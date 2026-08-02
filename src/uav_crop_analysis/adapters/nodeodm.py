"""Docker-managed local NodeODM runtime and PyODM orthomosaic adapter."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
from typing import Any
from urllib.request import urlopen

from uav_crop_analysis.errors import GeospatialError
from uav_crop_analysis.geospatial.ports import ImageReference, ProgressCallback


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
HealthProbe = Callable[[str], bool]
DesktopLauncher = Callable[[], bool]


class DockerNodeOdmRuntime:
    """Ensures a private local NodeODM container is ready for PyODM."""

    def __init__(
        self,
        *,
        image: str = "opendronemap/nodeodm:latest",
        container_name: str = "uav-crop-nodeodm",
        node_url: str = "http://127.0.0.1:3000",
        docker_executable: str | Path | None = None,
        startup_timeout: float = 180.0,
        runner: CommandRunner | None = None,
        health_probe: HealthProbe | None = None,
        sleeper: Callable[[float], None] | None = None,
        desktop_launcher: DesktopLauncher | None = None,
    ) -> None:
        self.image = image
        self.container_name = container_name
        self.node_url = node_url.rstrip("/")
        self.docker_executable = str(docker_executable) if docker_executable else None
        self.startup_timeout = startup_timeout
        self._runner = runner or subprocess.run
        self._health_probe = health_probe or self._probe_node
        self._sleep = sleeper or time.sleep
        self._desktop_launcher = desktop_launcher or self._launch_docker_desktop

    def ensure_running(
        self,
        progress: ProgressCallback | None = None,
    ) -> dict[str, object]:
        self._emit(progress, 0.02, "Kiểm tra Docker")
        docker = self._resolve_docker()
        info = self._run(docker, "info", "--format", "{{.ServerVersion}}", timeout=20)
        if info.returncode != 0:
            self._emit(progress, 0.03, "Đang khởi động Docker Desktop")
            if not self._desktop_launcher():
                raise GeospatialError(
                    "Docker đã được cài nhưng Docker Desktop/daemon chưa chạy. "
                    f"Hãy mở Docker rồi thử lại. {self._detail(info)}"
                )
            info = self._wait_for_docker(docker)
        docker_version = info.stdout.strip()

        if self._health_probe(self.node_url):
            self._emit(progress, 0.20, "NodeODM đã sẵn sàng")
            return self._provenance(docker_version)

        image_status = self._run(docker, "image", "inspect", self.image, timeout=30)
        if image_status.returncode != 0:
            self._emit(
                progress,
                0.05,
                "Đang tải NodeODM lần đầu; thời gian phụ thuộc tốc độ mạng",
            )
            pulled = self._run(docker, "pull", self.image, timeout=3600)
            if pulled.returncode != 0:
                raise GeospatialError(
                    f"Không tải được image {self.image}. {self._detail(pulled)}"
                )

        self._emit(progress, 0.12, "Khởi động container NodeODM")
        container = self._run(
            docker,
            "container",
            "inspect",
            "--format",
            "{{.State.Running}}",
            self.container_name,
            timeout=30,
        )
        if container.returncode == 0:
            if container.stdout.strip().lower() != "true":
                started = self._run(
                    docker,
                    "start",
                    self.container_name,
                    timeout=120,
                )
                if started.returncode != 0:
                    raise GeospatialError(
                        f"Không khởi động được container NodeODM. {self._detail(started)}"
                    )
        else:
            started = self._run(
                docker,
                "run",
                "-d",
                "--name",
                self.container_name,
                "--restart",
                "unless-stopped",
                "-p",
                "127.0.0.1:3000:3000",
                self.image,
                timeout=180,
            )
            if started.returncode != 0:
                raise GeospatialError(
                    "Không tạo được container NodeODM. Kiểm tra cổng 3000 và Docker. "
                    f"{self._detail(started)}"
                )

        self._emit(progress, 0.15, "Chờ NodeODM sẵn sàng")
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self._health_probe(self.node_url):
                self._emit(progress, 0.20, "NodeODM đã sẵn sàng")
                return self._provenance(docker_version)
            self._sleep(1.0)

        logs = self._run(
            docker,
            "logs",
            "--tail",
            "30",
            self.container_name,
            timeout=30,
        )
        raise GeospatialError(
            "NodeODM không sẵn sàng sau khi khởi động container. "
            f"{self._detail(logs)}"
        )

    def _resolve_docker(self) -> str:
        if self.docker_executable:
            return self.docker_executable
        candidates = (
            shutil.which("docker"),
            "/usr/local/bin/docker",
            "/opt/homebrew/bin/docker",
            "/Applications/Docker.app/Contents/Resources/bin/docker",
        )
        executable = next(
            (str(path) for path in candidates if path and Path(path).is_file()),
            None,
        )
        if executable is None:
            raise GeospatialError(
                "Không tìm thấy Docker. Hãy cài Docker Desktop rồi chạy lại tác vụ."
            )
        return executable

    def _wait_for_docker(self, docker: str) -> subprocess.CompletedProcess[str]:
        deadline = time.monotonic() + 180.0
        latest = self._run(docker, "info", "--format", "{{.ServerVersion}}", timeout=20)
        while latest.returncode != 0 and time.monotonic() < deadline:
            self._sleep(2.0)
            latest = self._run(
                docker,
                "info",
                "--format",
                "{{.ServerVersion}}",
                timeout=20,
            )
        if latest.returncode != 0:
            raise GeospatialError(
                "Docker Desktop không sẵn sàng sau khi app thử khởi động. "
                f"{self._detail(latest)}"
            )
        return latest

    @staticmethod
    def _launch_docker_desktop() -> bool:
        system = platform.system()
        try:
            if system == "Darwin" and Path("/Applications/Docker.app").exists():
                subprocess.Popen(
                    ["open", "-a", "Docker"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            if system == "Windows":
                program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
                executable = program_files / "Docker/Docker/Docker Desktop.exe"
                if executable.is_file():
                    subprocess.Popen(
                        [str(executable)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
        except OSError:
            return False
        return False

    def _run(
        self,
        docker: str,
        *arguments: str,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(
                [docker, *arguments],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GeospatialError(f"Không thể chạy Docker: {exc}") from exc

    def _provenance(self, docker_version: str) -> dict[str, object]:
        return {
            "runtime": "docker",
            "docker_version": docker_version,
            "image": self.image,
            "container_name": self.container_name,
            "node_url": self.node_url,
        }

    @staticmethod
    def _probe_node(node_url: str) -> bool:
        try:
            with urlopen(f"{node_url}/info", timeout=2) as response:
                return response.status == 200
        except OSError:
            return False

    @staticmethod
    def _detail(completed: subprocess.CompletedProcess[str]) -> str:
        return (completed.stderr or completed.stdout or "").strip()[-1200:]

    @staticmethod
    def _emit(
        progress: ProgressCallback | None,
        value: float,
        status: str,
    ) -> None:
        if progress is not None:
            progress(value, status)


class DockerManagedNodeOdmEngine:
    """Creates an orthomosaic through a managed NodeODM container and PyODM."""

    display_name = "NodeODM (Docker local)"

    def __init__(
        self,
        *,
        runtime: DockerNodeOdmRuntime | None = None,
        timeout: int = 30,
        options: dict[str, object] | None = None,
        node_factory: Callable[[str, int], Any] | None = None,
    ) -> None:
        self.runtime = runtime or DockerNodeOdmRuntime()
        self.timeout = timeout
        self.options = options or {
            "auto-boundary": True,
            "feature-quality": "high",
            "matcher-neighbors": 8,
            "orthophoto-resolution": 1.0,
        }
        self._node_factory = node_factory

    @property
    def public_location(self) -> str:
        return self.runtime.node_url

    def create(
        self,
        mission_id: str,
        image_paths: tuple[Path, ...],
        output_dir: Path,
        *,
        image_references: tuple[ImageReference, ...] = (),
        progress: ProgressCallback | None = None,
    ) -> tuple[Path, dict[str, object]]:
        if len(image_paths) < 2:
            raise GeospatialError("NodeODM cần ít nhất hai ảnh nguồn")
        missing = [str(path) for path in image_paths if not path.is_file()]
        if missing:
            raise GeospatialError(f"Không tìm thấy ảnh nguồn NodeODM: {missing[0]}")

        runtime_provenance = self.runtime.ensure_running(progress)
        directory = output_dir.expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        prepared_images = self._prepare_images(directory, image_paths)
        uploads = [str(path.resolve()) for path in prepared_images]
        options = dict(self.options)
        source_gsds = tuple(
            reference.gsd_cm_per_px
            for reference in image_references
            if reference.gsd_cm_per_px is not None and reference.gsd_cm_per_px > 0
        )
        if source_gsds:
            # Do not upsample the lowest-resolution camera in a mixed-drone mission.
            options["orthophoto-resolution"] = round(max(source_gsds), 6)
            self._emit(
                progress,
                0.20,
                "Độ phân giải orthophoto theo GSD nguồn: "
                f"{options['orthophoto-resolution']:.4g} cm/pixel",
            )
        geo_file = self._write_geo_file(
            directory,
            image_paths,
            prepared_images,
            image_references,
        )
        if geo_file is not None:
            uploads.append(str(geo_file))
            options["geo"] = geo_file.name

        try:
            node = self._make_node()
            task = node.create_task(
                uploads,
                options,
                name=mission_id,
                progress_callback=(
                    (
                        lambda value: self._emit(
                            progress,
                            0.20 + float(value) / 100.0 * 0.15,
                            f"Đang gửi ảnh lên NodeODM: {float(value):.0f}%",
                        )
                    )
                    if progress
                    else None
                ),
            )

            def status_callback(info: Any) -> None:
                if progress is not None:
                    value = float(getattr(info, "progress", 0.0))
                    status = str(getattr(info, "status", "running"))
                    self._emit(
                        progress,
                        0.35 + value / 100.0 * 0.55,
                        f"NodeODM đang xử lý: {status} ({value:.0f}%)",
                    )

            task.wait_for_completion(status_callback=status_callback)
            self._emit(progress, 0.92, "Đang tải orthophoto GeoTIFF")
            destination = Path(task.download_assets(str(directory))).resolve()
        except GeospatialError:
            raise
        except Exception as exc:
            raise GeospatialError(f"Tác vụ NodeODM thất bại: {exc}") from exc

        candidates = tuple(destination.rglob("odm_orthophoto.tif"))
        if len(candidates) != 1:
            raise GeospatialError(
                "Kết quả NodeODM không chứa đúng một file odm_orthophoto.tif"
            )
        self._emit(progress, 1.0, "Đã mở orthophoto GeoTIFF")
        return candidates[0], {
            "engine": self.display_name,
            "task_id": str(task.uuid),
            "options": options,
            "orthophoto_resolution_cm_per_px": options["orthophoto-resolution"],
            "source_gsd_cm_per_px": source_gsds,
            "orthophoto_resolution_strategy": (
                "coarsest_source_gsd" if source_gsds else "engine_default"
            ),
            "source_image_count": len(image_paths),
            **runtime_provenance,
        }

    def _make_node(self) -> Any:
        if self._node_factory is not None:
            return self._node_factory(self.runtime.node_url, self.timeout)
        try:
            from pyodm import Node
        except ImportError as exc:
            raise GeospatialError("Bản cài thiếu PyODM") from exc
        return Node.from_url(self.runtime.node_url, timeout=self.timeout)

    @staticmethod
    def _prepare_images(
        directory: Path,
        image_paths: tuple[Path, ...],
    ) -> tuple[Path, ...]:
        duplicate_names = {
            name
            for name, count in Counter(path.name for path in image_paths).items()
            if count > 1
        }
        if not duplicate_names:
            return tuple(path.resolve() for path in image_paths)
        staging = directory / "images"
        staging.mkdir(parents=True, exist_ok=True)
        prepared: list[Path] = []
        for index, source in enumerate(image_paths):
            target = staging / f"{index:06d}_{source.name}"
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
            prepared.append(target)
        return tuple(prepared)

    @staticmethod
    def _write_geo_file(
        directory: Path,
        source_paths: tuple[Path, ...],
        upload_paths: tuple[Path, ...],
        references: tuple[ImageReference, ...],
    ) -> Path | None:
        if not references:
            return None
        reference_by_path = {reference.path.resolve(): reference for reference in references}
        lines = ["EPSG:4326"]
        for source_path, upload_path in zip(source_paths, upload_paths, strict=True):
            reference = reference_by_path.get(source_path.resolve())
            if reference is None:
                continue
            altitude = reference.altitude_m if reference.altitude_m is not None else 0.0
            lines.append(
                f"{upload_path.name} {reference.longitude:.10f} "
                f"{reference.latitude:.10f} {altitude:.3f}"
            )
        if len(lines) == 1:
            return None
        geo_file = directory / "geo.txt"
        geo_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return geo_file

    @staticmethod
    def _emit(
        progress: ProgressCallback | None,
        value: float,
        status: str,
    ) -> None:
        if progress is not None:
            progress(value, status)
