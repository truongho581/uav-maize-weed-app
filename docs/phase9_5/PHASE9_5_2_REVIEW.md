# Review Phase 9.5.2 - Lõi mission planner

## Kết quả

Đã bổ sung lõi lập kế hoạch deterministic cho polygon WGS84 và một đến ba drone. Planner
tính footprint/GSD, sinh điểm dừng-chụp, chia làn liền kề, ước lượng route và tự kiểm tra
coverage trước khi trả kết quả.

## Thành phần

- `planning/models.py`: request, profile, footprint, waypoint, route, warning và plan.
- `planning/ports.py`: `MissionPlanner` và `MissionPlanRepository` protocol.
- `planning/service.py`: `GridMissionPlanner` dùng Shapely/pyproj.
- `MissionPlanningError`: exception ổn định cho SDK/API phase sau.
- `shapely==2.1.2`, `pyproj==3.7.2`: dependency runtime đã khóa trong `uv.lock`.
- PyInstaller và hook được đưa vào dependency dev để build từ máy sạch tái lập được.

## Hành vi đã kiểm tra

- Công thức footprint, suy VFOV từ HFOV và tỷ lệ ảnh, GSD X/Y.
- Từ chối camera thiếu geometry, polygon tự cắt và profile ngoài miền.
- Hình chữ nhật với 1, 2, 3 drone; lane liền kề và waypoint nằm trong polygon.
- Polygon lõm và polygon xoay 27 độ.
- Heading tự động theo trục dài.
- Camera FOV hẹp tạo nhiều làn/điểm hơn camera FOV rộng.
- Thiếu home vẫn preview nhưng `export_ready=false`.
- Cảnh báo khoảng cách route và từ chối khi số làn ít hơn số drone.
- Hai lần chạy cùng input trả dataclass bằng nhau.
- Coverage fixture hình chữ nhật/lõm đạt từ `0.999999` đến `1.0`.

## Quality gate

- Test planner: 20 test đạt.
- Toàn bộ test suite: 185 test đạt.
- `ruff check .`: đạt.
- MyPy riêng package planning/test với `--follow-imports=skip`: đạt.
- MyPy toàn repository còn 15 lỗi nền ở năm file cũ, không tăng so với Phase 9.5.1.
- Wheel chứa đủ bốn module `uav_crop_analysis.planning`: đạt.
- PyInstaller nhận hook Shapely, pyproj và runtime hook PROJ: đạt.
- Bundle chính build/re-sign và smoke tới Qt event loop: đạt.
- SHA-256 executable: `a486d5ffc6d1a62653db83d6bf83469a4b220d573ce8ed8b05503af5ad028ce7`.

## Giới hạn còn lại

- Chưa persistence plan và draft.
- Chưa schema JSON, checksum bundle hoặc writer QGroundControl.
- Chưa SDK/CLI/REST endpoint.
- Chưa UI vẽ polygon và xem route.
- Chưa terrain following, obstacle/no-fly/geofence, pin/gió và tránh va chạm động.

## Kết luận

Lõi Phase 9.5.2 đáp ứng contract hình học cần thiết để chuyển sang Phase 9.5.3: định dạng
GreenEye mission, persistence/export, QGC writer và public SDK/API.
