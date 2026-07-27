from __future__ import annotations

from collections.abc import Iterator
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from uav_crop_analysis.api import ApiApplication, LocalApiServer
import uav_crop_analysis.bootstrap as bootstrap_module
from uav_crop_analysis.bootstrap import build_runtime
from uav_crop_analysis.cli import main as cli_main
from uav_crop_analysis.errors import ConfigurationError, MissionNotFoundError
from uav_crop_analysis.infrastructure import AppConfig, AppPaths
from uav_crop_analysis.sdk import (
    CreateMissionRequest,
    UavCropAnalysis,
    to_json_value,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "models/model_inventory.json"


@pytest.fixture
def sdk(tmp_path: Path) -> Iterator[UavCropAnalysis]:
    paths = AppPaths(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    )
    runtime = build_runtime(
        tmp_path / "ứng dụng phase 9.db",
        config=AppConfig(paths),
        registry_path=REGISTRY,
        nodeodm_url="",
    )
    value = UavCropAnalysis(runtime)
    yield value
    runtime.shutdown()


def _mission_request(mission_id: str = "mission-phase9") -> CreateMissionRequest:
    return CreateMissionRequest(
        mission_id=mission_id,
        name="Khảo sát tích hợp ba drone",
        drone_ids=("drone-01", "drone-02", "drone-03"),
    )


def test_sdk_is_qt_independent_and_exposes_read_only_capabilities(
    sdk: UavCropAnalysis,
) -> None:
    command = [
        sys.executable,
        "-c",
        (
            "import sys; import uav_crop_analysis.sdk; "
            "print(any(name.startswith('PySide6') for name in sys.modules))"
        ),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT / "src")},
    )
    assert completed.stdout.strip() == "False"

    capabilities = to_json_value(sdk.capabilities())
    assert capabilities["api_versions"] == ["v1"]
    assert capabilities["drone_commands_enabled"] is False
    assert capabilities["mission_management"] is True


def test_runtime_creates_artifact_free_registry_for_plain_wheel_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = AppPaths(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    )

    def no_pack(_override: object = None) -> Path:
        raise FileNotFoundError("no model pack")

    monkeypatch.setattr(bootstrap_module, "resolve_registry_path", no_pack)
    runtime = build_runtime(tmp_path / "fallback.db", config=AppConfig(paths))
    try:
        assert runtime.registry_path == paths.config_dir / "model_inventory.json"
        assert runtime.registry_path.is_file()
        models = runtime.catalog.list_models()
        assert len(models) == 5
        assert not any(model.available for model in models)
    finally:
        runtime.shutdown()


def test_sdk_create_list_get_and_missing_mission(sdk: UavCropAnalysis) -> None:
    created = sdk.create_mission(_mission_request())

    assert created.mission_id == "mission-phase9"
    assert [item.lane_index for item in created.drones] == [0, 1, 2]
    assert sdk.list_missions() == (created,)
    assert sdk.get_mission(created.mission_id) == created
    with pytest.raises(MissionNotFoundError):
        sdk.get_mission("missing")


def test_api_v1_contract_and_backward_compatible_key_set(sdk: UavCropAnalysis) -> None:
    application = ApiApplication(sdk)
    created = application.handle(
        "POST",
        "/api/v1/missions",
        json.dumps(
            {
                "mission_id": "api-mission",
                "name": "Nhiệm vụ API",
                "drone_ids": ["uav-1", "uav-2", "uav-3"],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    assert created.status == 201
    assert set(created.payload) == {"api_version", "data"}
    assert created.payload["api_version"] == "v1"
    assert set(created.payload["data"]) == {
        "mission_id",
        "name",
        "created_at",
        "drones",
        "altitude_m",
        "gimbal_pitch_deg",
        "forward_overlap",
        "side_overlap",
        "capture_mode",
        "image_count",
        "gps_coverage",
        "data_status",
    }
    assert application.handle("GET", "/api/v1/missions").payload["data"][0][
        "name"
    ] == "Nhiệm vụ API"
    assert application.handle("GET", "/api/v1/missions/api-mission/jobs").payload[
        "data"
    ] == []
    assert application.handle(
        "GET", "/api/v1/missions/api-mission/results"
    ).payload["data"] == []
    report = application.handle("GET", "/api/v1/missions/api-mission/report")
    assert report.status == 200
    assert report.payload["data"]["mission_id"] == "api-mission"
    missing = application.handle("GET", "/api/v1/missions/không-có")
    assert missing.status == 404
    assert missing.payload["error"]["code"] == "mission_not_found"


def test_local_http_server_health_create_and_security_headers(
    sdk: UavCropAnalysis,
) -> None:
    with LocalApiServer(ApiApplication(sdk), port=0) as server:
        host, port = server.address
        base = f"http://{host}:{port}/api/v1"
        with urlopen(f"{base}/health", timeout=3) as response:
            payload = json.load(response)
            assert response.headers["Cache-Control"] == "no-store"
        assert payload["data"]["database_schema_version"] == 3

        request = Request(
            f"{base}/missions",
            data=json.dumps(
                {
                    "mission_id": "http-mission",
                    "name": "Mission HTTP",
                    "drone_ids": ["d1", "d2", "d3"],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            assert response.status == 201
            assert json.load(response)["data"]["mission_id"] == "http-mission"

        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}/missions/missing", timeout=3)
        assert error.value.code == 404


def test_local_api_refuses_remote_bind_without_explicit_override(
    sdk: UavCropAnalysis,
) -> None:
    with pytest.raises(ConfigurationError):
        LocalApiServer(ApiApplication(sdk), host="0.0.0.0", port=0)


def test_cli_creates_and_lists_unicode_mission(tmp_path: Path) -> None:
    database = tmp_path / "cli dữ liệu.db"
    created_output = StringIO()
    common = ["--database", str(database), "--registry", str(REGISTRY)]
    status = cli_main(
        [
            *common,
            "mission",
            "create",
            "cli-mission",
            "--name",
            "Khảo sát CLI",
            "--drone",
            "drone-01",
            "--drone",
            "drone-02",
            "--drone",
            "drone-03",
        ],
        stdout=created_output,
    )
    assert status == 0
    assert json.loads(created_output.getvalue())["name"] == "Khảo sát CLI"

    listed_output = StringIO()
    assert cli_main([*common, "mission", "list"], stdout=listed_output) == 0
    assert json.loads(listed_output.getvalue())[0]["mission_id"] == "cli-mission"
