# Review Phase 9.5.3 - Export và contract tích hợp

## Kết quả

Phase 9.5.3 hoàn thành phần lưu, đọc lại, lập và xuất kế hoạch qua SDK, CLI và REST. Kế hoạch
được lưu độc lập với Qt; runtime desktop, module Python, CLI và local API dùng cùng một
`MissionPlanningService`.

## Thành phần đã thêm

- GreenEye mission contract version 1 và JSON Schema đóng cùng package.
- Fingerprint SHA-256 của camera profile trong plan để truy vết cấu hình đã dùng.
- Repository JSON atomic, tên file hash theo mission ID và thay thế plan cùng ID.
- Bundle exporter atomic gồm `mission.json`, route JSON, QGC `.plan` và checksum.
- QGC writer dùng waypoint dừng và lệnh chụp một ảnh, đọc ngược được bằng reader Phase 9.
- SDK: plan/list/get/export.
- CLI: `plan create/list/show/export` và tùy chọn `--plan-store`.
- REST v1: create/list/get/export mission plan.
- Capabilities mới: `mission_planning`, `mission_plan_export`,
  `qgroundcontrol_plan_export`; `drone_commands_enabled=false` được giữ nguyên.
- Persistence location có thể đổi bằng SDK, CLI hoặc `UAV_CROP_MISSION_PLAN_DIR`.

## Kiểm tra

- `pytest -q`: **194 passed**.
- Test mới Phase 9.5.3: schema/round-trip, persistence, portable paths, checksum, missing
  home, QGC reader round-trip, golden shape, SDK restart, REST và CLI.
- `ruff check .`: đạt.
- MyPy trên 16 file mới/chạm trong phase: đạt.
- MyPy toàn repo: còn đúng 15 lỗi đã tồn tại trong 5 file UI/tool/worker; phase này không tạo
  lỗi type mới.
- PyInstaller macOS arm64: build và ký lại framework thành công.
- Schema có trong bundle tại
  `_internal/uav_crop_analysis/resources/schemas/greeneye-mission-plan.schema.json`.
- Frozen offscreen smoke: runtime đi vào Qt event loop; tiến trình test đã được dừng sau khi
  xác nhận.
- SHA-256 executable:
  `0a06a1df0c81883836ed402be048d358043c44519c549513118741e64dd9f439`.

## Quyết định an toàn

- GreenEye chỉ tạo file; không có endpoint arm, takeoff, upload hoặc start.
- Chỉ plan có home cho mọi drone mới được xuất.
- QGC adapter mặc định metadata ArduPilot multirotor và phải được người vận hành kiểm tra
  lại theo autopilot/camera thật trước upload.
- Chưa tuyên bố tương thích bay thật, terrain following, geofence, tránh va chạm hoặc SITL
  đa vehicle.

## Việc còn lại

Phase 9.5.4 sẽ thêm màn **Lập nhiệm vụ**: vẽ/import polygon, chọn camera và home, xem route
1-3 drone, bảng waypoint, lưu draft và export dialog. Review trực quan trong ứng dụng
QGroundControl thật và SITL vẫn thuộc Phase 9.5.6.
