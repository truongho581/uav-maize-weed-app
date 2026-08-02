# Phase 9 - SDK, CLI và REST API contract

## Versioning

- Package/SDK: SemVer `0.2.0`.
- SDK DTO: `SDK_SCHEMA_VERSION = 1`.
- REST: `/api/v1`; response luôn chứa `api_version: "v1"`.
- Thêm field là thay đổi tương thích. Xóa/đổi tên field hoặc đổi ý nghĩa cần API version mới.

SDK entry point là `uav_crop_analysis.sdk.UavCropAnalysis`. Import SDK không import Qt.
Desktop, CLI và REST cùng dùng `build_runtime`, SQLite repository và application service;
không có đường nghiệp vụ riêng cho API.

Nếu bản wheel không đi cùng model pack, runtime tạo registry fallback trong config user với
đủ model manifest nhưng không có artifact. Mission/API vẫn hoạt động; inference bị khóa cho
tới khi host cung cấp `registry_path` hoặc `UAV_CROP_MODEL_REGISTRY` có checkpoint hợp lệ.

## Python SDK

Các nhóm phương thức ổn định:

- Mission: `create_mission`, `import_manifest`, `list_missions`, `get_mission`.
- Job: `submit_analysis`, `list_jobs`, `get_job`, `cancel_job`.
- Result: `list_results`, `build_report`, `export_report`.
- Integration: `inspect_qgc_plan`, `read_qgc_log`, `capabilities`.

Mission chấp nhận từ một đến ba `drone_ids` duy nhất. Lane được gán liên tục theo thứ
tự đầu vào từ `0` đến `n-1`; 0 hoặc hơn 3 drone bị từ chối.

```python
from uav_crop_analysis.sdk import CreateMissionRequest, UavCropAnalysis

with UavCropAnalysis.open("app.db") as sdk:
    mission = sdk.create_mission(
        CreateMissionRequest(
            mission_id="field-a",
            name="Field A",
            drone_ids=("drone-01", "drone-02", "drone-03"),
        )
    )
```

## CLI

```text
uav-crop version
uav-crop capabilities
uav-crop mission create ID --name NAME --drone D1 [--drone D2] [--drone D3]
uav-crop mission import mission.json
uav-crop mission list
uav-crop job submit MISSION_ID --model MODEL_ID --artifact best
uav-crop job show JOB_ID
uav-crop report MISSION_ID --output reports/
uav-crop qgc-plan survey.plan
uav-crop qgc-log MISSION_ID flight.csv --map-system 1=drone-01
uav-crop serve --host 127.0.0.1 --port 8765
```

CLI ghi JSON UTF-8 ra stdout; lỗi ghi JSON ra stderr và trả exit code `2`.

## REST endpoints

| Method | Path | Nội dung |
| --- | --- | --- |
| GET | `/api/v1/health` | Health và database schema |
| GET | `/api/v1/version` | App/SDK/API version |
| GET | `/api/v1/capabilities` | Tính năng và safety state |
| GET, POST | `/api/v1/missions` | Danh sách/tạo mission 1-3 drone |
| POST | `/api/v1/missions/import` | Import `mission.json` |
| GET | `/api/v1/missions/{id}` | Mission read model |
| GET, POST | `/api/v1/missions/{id}/jobs` | Danh sách/tạo analysis job |
| GET | `/api/v1/jobs/{id}` | Poll trạng thái job |
| POST | `/api/v1/jobs/{id}/cancel` | Yêu cầu hủy job |
| GET | `/api/v1/missions/{id}/results` | Spatial result |
| GET | `/api/v1/missions/{id}/report` | Report schema 1 |
| POST | `/api/v1/missions/{id}/report/export` | Xuất report portable |
| POST | `/api/v1/integrations/qgc/plan` | Đọc QGC Plan |
| POST | `/api/v1/integrations/qgc/log` | Đọc QGC CSV/tlog |
| GET | `/api/v1/integrations/simulation` | Ba telemetry stream mô phỏng |

Success envelope:

```json
{"api_version": "v1", "data": {}}
```

Error envelope:

```json
{
  "api_version": "v1",
  "error": {"code": "mission_not_found", "message": "...", "context": {}}
}
```

## Security boundary

- Server bind `127.0.0.1` mặc định và từ chối địa chỉ non-loopback nếu thiếu
  `allow_remote=True`/`--allow-remote`.
- Request body tối đa 1 MiB; response JSON dùng `no-store` và `nosniff`.
- API không phục vụ file tùy ý và không có endpoint điều khiển drone.
- `--allow-remote` chỉ mở bind; chưa bổ sung authentication/TLS nên không dùng trên mạng
  không tin cậy. Hardening authentication thuộc deployment host/Phase 11.
