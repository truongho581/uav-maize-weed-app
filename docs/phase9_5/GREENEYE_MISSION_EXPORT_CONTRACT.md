# Phase 9.5.3 - Contract xuất nhiệm vụ GreenEye

## Mục đích

GreenEye lập và lưu một kế hoạch khảo sát cho mission hiện hữu, sau đó xuất một bundle độc
lập với máy nguồn. Mission, thứ tự drone và camera profile đều lấy từ dữ liệu đã lưu trong
ứng dụng. Tọa độ public luôn theo thứ tự `[latitude, longitude]` và hệ WGS84.

Phase này chỉ tạo file để người vận hành kiểm tra trong phần mềm điều khiển. GreenEye không
arm, upload, cất cánh hay bắt đầu nhiệm vụ trên drone.

## Bundle đầu ra

```text
GreenEye mission/
  <mission-id>/
  mission.json
  qgroundcontrol/
    drone-01.plan
    drone-02.plan
    drone-03.plan
  media/
    README.txt
    drone-01/
    drone-02/
    drone-03/
  checksums.sha256
```

- Số file route bằng đúng số drone của mission, từ 1 đến 3.
- `mission.json` dùng schema version 1 và chứa polygon, profile bay, fingerprint camera,
  footprint/GSD, route, waypoint, cảnh báo và thống kê coverage.
- `qgroundcontrol/*.plan` dùng QGC Plan version 1 và Mission version 2; đây là file dùng để
  mở, kiểm tra và nạp vào QGroundControl cho từng drone.
- Sau chuyến bay, chép ảnh của từng drone vào `media/<drone-id>/`; có thể đặt
  `telemetry.csv` hoặc `flight-log.csv` cùng thư mục. Ứng dụng ghi nhớ thư viện đã xuất và tự
  nhận media hợp lệ khi được mở lại.
- `checksums.sha256` dùng SHA-256 cho `mission.json` và các file `.plan`, chỉ ghi đường dẫn POSIX tương đối.
- Không file nào trong bundle ghi đường dẫn tuyệt đối của máy tạo bundle.

JSON Schema được đóng cùng package tại
`uav_crop_analysis/resources/schemas/greeneye-mission-plan.schema.json` và có thể đọc bằng
`uav_crop_analysis.planning.load_mission_plan_schema()`.

## QGroundControl adapter

Mỗi điểm dừng-chụp sinh hai `SimpleItem`:

1. `MAV_CMD_NAV_WAYPOINT` (`16`) với `param1` là thời gian giữ tại điểm.
2. `MAV_CMD_DO_SET_CAM_TRIGG_DIST` (`206`) với `param3=1` để yêu cầu chụp một ảnh.

Altitude dùng `MAV_FRAME_GLOBAL_RELATIVE_ALT` và được hiểu là AGL tương đối điểm home theo
giới hạn hiện tại của planner. Adapter mặc định metadata ArduPilot multirotor; người vận hành
phải mở và kiểm tra file trong QGroundControl, đối chiếu autopilot/camera thực tế trước khi
upload. GreenEye chưa thêm lệnh arm, takeoff hoặc start.

## Persistence

Plan mới thay thế plan cũ có cùng `mission_id` và tồn tại sau khi mở lại app. Mặc định plan
được lưu trong `<app-data>/mission-plans`. Host có thể đổi vị trí bằng:

- Python: `UavCropAnalysis.open(..., mission_plan_path=...)`.
- CLI: `--plan-store PATH`.
- Environment: `UAV_CROP_MISSION_PLAN_DIR`.

Tên file persistence là SHA-256 của mission ID để mission ID không thể tạo path traversal.

## Python SDK

```python
from uav_crop_analysis.sdk import PlanMissionRequest, UavCropAnalysis

with UavCropAnalysis.open() as sdk:
    plan = sdk.plan_mission(
        PlanMissionRequest(
            mission_id="field-01",
            camera_profile_id="camera-rgb",
            polygon_wgs84=((10.1, 106.1), (10.1, 106.2), (10.2, 106.2)),
            homes_wgs84=((10.1, 106.1),),
        )
    )
    exported = sdk.export_mission_plan(plan.mission_id, "exports")
```

SDK còn có `list_mission_plans()` và `get_mission_plan(mission_id)`. Camera profile phải được
lưu trước. Số drone và thứ tự route được lấy từ assignment của mission.

## CLI

```bash
uav-crop plan create request.json
uav-crop plan list
uav-crop plan show field-01
uav-crop plan export field-01 --output exports
```

`request.json` dùng các field của `PlanMissionRequest`; bắt buộc có `mission_id`,
`camera_profile_id` và `polygon_wgs84`. Chỉ plan có home cho mọi drone mới được xuất.

## REST v1

```text
POST /api/v1/mission-plans
GET  /api/v1/mission-plans
GET  /api/v1/mission-plans/{mission_id}
POST /api/v1/mission-plans/{mission_id}/export
```

Body export là `{"output_root": "..."}`. `GET /api/v1/capabilities` công bố
`mission_planning`, `mission_plan_export` và `qgroundcontrol_plan_export`; trường
`drone_commands_enabled` vẫn là `false`.

## Giới hạn an toàn

- Chưa có terrain following, DEM, geofence/no-fly database hoặc tránh va chạm động.
- Fingerprint camera giúp phát hiện camera profile thay đổi, không thay thế hiệu chuẩn lens.
- Trigger ảnh phụ thuộc autopilot và camera adapter hỗ trợ lệnh MAVLink tương ứng.
- File QGC là đầu ra để review; chưa được tuyên bố đã kiểm thử bay thật hoặc SITL đa vehicle.

## Tài liệu định dạng đối chiếu

- [QGroundControl Plan File Format](https://docs.qgroundcontrol.com/master/en/qgc-dev-guide/file_formats/plan.html)
- [MAVLink Common Message Set](https://mavlink.io/en/messages/common.html)
