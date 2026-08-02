# Review Phase 9.5.4 - Giao diện lập nhiệm vụ

## Kết quả

Phase 9.5.4 hoàn thành màn **Lập nhiệm vụ** trong desktop app. Người dùng có thể vẽ hoặc
import polygon WGS84, chọn camera và cấu hình dừng-chụp, đặt home cho một đến ba drone,
tính route, kiểm tra waypoint và xuất bundle đã được định nghĩa ở Phase 9.5.3.

## Thành phần đã thêm

- `PlanningWorkspaceViewModel` độc lập Qt widget, dùng chung service persistence/planner.
- `MissionPlannerPage` với bố cục ba vùng và trạng thái bận/lỗi/kế hoạch cũ.
- Bản đồ Leaflet + Esri satellite qua Qt WebEngine/WebChannel.
- Vẽ, sửa, hoàn tác, xóa, import polygon và vừa khung.
- Tắt/bật route, chỉ số tổng/route, cảnh báo tiếng Việt và bảng waypoint ảo.
- Draft tự lưu theo mission bằng `QSettings`.
- Khóa xuất nếu thay đổi draft sau khi tính hoặc thiếu home.
- Navigation shell, controller nền cho calculate/export và thông báo trạng thái.
- Qt WebChannel trong cấu hình PyInstaller.

## Kiểm tra

- `pytest -q`: **201 passed**.
- Test mới: parser tọa độ, draft restore, stale plan, view-model calculate/persist/export,
  contract HTML bản đồ và shell navigation.
- `ruff check .`: đạt.
- MyPy trên bốn module UI/app chạm trong phase: đạt.
- Ảnh review:
  - `review_screenshots/latest-planning-1180x760.png`
  - `review_screenshots/latest-planning-1440x900.png`
  - `review_screenshots/latest-planning-1920x1080.png`
- PyInstaller macOS arm64: build và ký lại 124 framework thành công.
- Bundle có `PySide6/QtWebChannel.abi3.so`, QtWebChannel framework và GreenEye schema.
- Frozen offscreen smoke: executable duy trì Qt event loop 15 giây, không có lỗi khởi tạo.
- SHA-256 executable:
  `2b64a265f962bade413cd72cdde5ebcd8426526ae9261c193fca1b8e6d30748d`.

## Review trực quan

- Ba panel không bị cắt hoặc chồng chữ ở ba kích thước kiểm tra.
- Bản đồ là vùng trung tâm lớn nhất; bảng waypoint dùng phần dưới thay vì chiếm cột bên.
- Cột thiết lập và route giữ chiều rộng giới hạn, bảng route không còn cuộn ngang thừa.
- Nút bản đồ dùng biểu tượng và tooltip; thông số nâng cao nằm trong dialog.
- Route có màu và kiểu nét riêng; bảng chọn route dùng cùng màu để liên kết thị giác.

## Quyết định an toàn

- UI chỉ preview và xuất tệp, không có lệnh điều khiển drone.
- Kế hoạch cũ không thể xuất nhầm sau khi đổi altitude, overlap, polygon, camera hoặc home.
- Thiếu home vẫn cho preview nhưng khóa export.
- Bản đồ nền không được dùng như bằng chứng ranh giới, địa hình hoặc an toàn bay.

## Việc còn lại

Phase 9.5.5 bổ sung trợ giúp có version, sidebar mở rộng/thu gọn và hoàn thiện nhận diện
GreenEye. Phase 9.5.6 mới thực hiện review bằng QGroundControl thật, SITL và checklist
release; chưa tuyên bố sẵn sàng bay thật ở Phase 9.5.4.
