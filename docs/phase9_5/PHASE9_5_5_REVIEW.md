# Review Phase 9.5.5 - Trợ giúp, sidebar và GreenEye

## Kết quả

Phase 9.5.5 hoàn thành đổi nhận diện hiển thị sang GreenEye, sidebar có thể mở rộng/thu gọn
và hệ thống trợ giúp ngắn theo ngữ cảnh. Namespace lưu trữ và API/package cũ được giữ để
không làm mất hoặc tách dữ liệu người dùng khi nâng cấp.

## Thành phần đã thêm

- Hằng số branding tách tên hiển thị khỏi định danh lưu trữ.
- Icon mắt GreenEye cho application/window và sidebar.
- Sidebar 56/212 px, nhãn tiếng Việt, tooltip, accessible name và persistence QSettings.
- `InfoButton`, `HelpDialog`, tám nội dung trợ giúp và version nội dung `1.0`.
- Phím trợ giúp chuẩn của hệ điều hành.
- Tài liệu sử dụng và design system đổi sang GreenEye, kèm ghi chú tương thích dữ liệu.

## Kiểm tra

- `pytest -q`: **205 passed**.
- Test mới: display name/legacy namespace, sidebar persist/restore, contextual help, version,
  tooltip, accessible name và responsive 1180x760.
- `ruff check .`: đạt.
- MyPy trên bốn module UI/app chạm trong phase: đạt.
- Ảnh review:
  - `review_screenshots/latest-planning-1180x760.png`
  - `review_screenshots/latest-greeneye-sidebar-expanded-1180x760.png`
  - `review_screenshots/latest-greeneye-help.png`
- PyInstaller macOS arm64: build và ký lại 124 framework thành công.
- Bundle chứa icon trợ giúp/GreenEye và các resource UI mới.
- Frozen offscreen smoke: executable duy trì Qt event loop 15 giây, log rỗng.
- SHA-256 executable:
  `86d4825d2da406d28a97018745ee03d8c7041264c120f64c47be00298b2c46ec`.

## Review trực quan

- GreenEye và icon mắt là tín hiệu đầu tiên ở sidebar mở rộng.
- Sidebar thu gọn giữ viewer rộng như thiết kế trước; sidebar mở không che panel.
- Navigation có icon và chữ thẳng hàng; trạng thái chọn vẫn rõ trên nền xanh lá.
- Trợ giúp gọn, không che toàn màn hình, nội dung tiếng Việt và có provenance phiên bản.

## Quyết định tương thích

- Không đổi thư mục application support, QSettings namespace, package Python, CLI hoặc REST.
- Không thực hiện migration sao chép vì giữ nguyên định danh cũ là phương án ít rủi ro hơn.
- `UAV Crop Analysis` chỉ còn là tên kỹ thuật của storage/build; người dùng thấy GreenEye.

## Việc còn lại

Phase 9.5.6 thực hiện review tích hợp cuối: golden planner, build đa nền tảng, mở tệp trong
QGroundControl thật, SITL đa vehicle và checklist an toàn. Chưa tuyên bố sẵn sàng bay thật
trước khi các bước đó hoàn tất.
