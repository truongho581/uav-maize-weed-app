# Review Phase 9 - SDK/API và adapter phần mềm điều khiển

Ngày review: 2026-07-27.

## Đã hoàn thành

- Tách `build_runtime` khỏi Qt; desktop, SDK, CLI và REST dùng chung application service.
- Public SDK schema 1, package SemVer 0.2.0 và DTO JSON-safe.
- CLI `uav-crop` cho mission, job, report, QGC, simulation và API server.
- REST `/api/v1` cho health/version/capabilities, mission/job/result/report và QGC import.
- Local API loopback mặc định, giới hạn body và error envelope có code ổn định.
- QGC Plan reader giữ simple waypoint, survey polygon/transect, hover capture và overlap.
- QGC CSV log reader; `.tlog` dùng `pymavlink` optional.
- MAVSDK adapter chỉ đọc telemetry/download mission, reconnect có giới hạn.
- Guard mapping `system_id -> drone_id`, duplicate/out-of-order và demo ba stream mô phỏng.

## Safety review

- Không có phương thức arm/takeoff/land/upload/start hoặc endpoint gửi command.
- `drone_commands_enabled = false` trong capabilities.
- Remote bind phải bật rõ; chưa có authentication/TLS nên localhost là deployment mặc định.
- Simulation/SITL không được diễn giải là điều khiển realtime đã kiểm thử ngoài thực địa.

## Kiểm tra

- API v1 key-set/backward compatibility, Unicode, 404 và HTTP server thật.
- Server từ chối `0.0.0.0` khi không bật remote.
- SDK import không đưa PySide6 vào `sys.modules`.
- QGC simple/survey plan và CSV ba system.
- Duplicate system ID, mẫu lặp, dữ liệu sai thứ tự và reconnect.
- Adapter không có command method; desktop/offline chạy khi thiếu MAVSDK.

## Kết quả chốt phase

- Ruff: đạt, không có lỗi.
- MyPy: đạt trên 140 file nguồn/test/tool.
- Pytest: 114 test đạt, trong đó 13 test Phase 9.
- Visual regression: đạt ba screenshot Phase 7 và ba screenshot Phase 8.
- `uv lock --check`: lockfile hợp lệ, resolve 114 package; optional drone khóa MAVSDK
  3.17.2 và pymavlink 2.4.49.
- Đối chiếu runtime thật của MAVSDK 3.17.2: `System`, async position stream và
  `mission_raw.download_mission` tương thích adapter.
- Wheel `uav_crop_analysis-0.2.0-py3-none-any.whl`: 104 entry, có SDK/API/CLI/QGC/MAVSDK,
  hai console script và không có module legacy ở root.
- Wheel smoke ngoài source tree: fallback registry được tạo, CLI tạo mission ba drone và
  REST health trả database schema v3.
- PyInstaller macOS arm64: build thành công; bundle khoảng 736 MB.
- Frozen smoke: desktop khởi động từ user home sạch, database schema v3 và log không có lỗi.

## Giới hạn chuyển tiếp

- Chưa chạy ba PX4/ArduPilot SITL hoặc ba drone thật; Phase 9 dùng stream mô phỏng xác định.
- MAVSDK/tlog không nằm trong desktop dependency mặc định; cài optional extra `drone` cho
  host tích hợp.
- Không có authentication/TLS cho remote REST; deployment mặc định vẫn là loopback.
