# Phase 5 Review

## Phạm vi đã cài đặt

- PySide6 Qt Widgets shell mới là entry point mặc định.
- PyQt5 legacy được tách thành extra `legacy-ui` và entry point riêng.
- Design tokens, app shell, navigation, keyboard shortcuts và component states.
- Mission list dùng `QAbstractTableModel`, filter proxy và stable `mission_id` role.
- Mission Overview tổng hợp cấu hình bay, coverage ba drone và job gần đây.
- Viewmodel độc lập Qt; query service dùng repository ports.
- Command `analysisRequested(mission_id)` sẵn sàng để Phase 6 hoặc host xử lý.
- `PySide6-Essentials` chỉ cài Qt Core/Gui/Widgets; PyQt5 không còn là dependency mặc định.
- PyInstaller spec trỏ đúng cả project root và `src`, đồng thời không đóng gói runtime AI chưa dùng trong Phase 5.

## Ranh giới chủ ý

- Phase 5 chưa tạo analysis job từ UI. Chọn model, cấu hình inference và queue là Phase 6.
- Phase 5 chưa hiển thị image/layer viewer.
- UI hiện đọc SQLite local đồng bộ; dữ liệu hiện tại nhỏ và query không chạm AI. IPC/network query sau này cần loading state bất đồng bộ.
- Screenshot trên Windows/Linux chưa thể xác nhận từ máy macOS; checklist đã được lưu để chạy trên CI/máy build.
- PyInstaller phải build native riêng trên Windows, Linux và macOS; không dùng binary của hệ điều hành này cho hệ điều hành khác.

## Điều kiện review

- Mở mission và phát command phân tích trong tối đa ba bước.
- Mission rỗng vô hiệu hóa command và có tooltip giải thích.
- Lỗi repository không làm crash shell.
- Core/application import không kéo PySide6.
- Ba drone luôn hiển thị theo `lane_index` 0..2.

## Kết quả kiểm tra

- `pytest`: 81 test pass, coverage tổng 85%.
- `ruff check .`: pass.
- `mypy`: pass trên 88 source files.
- `uv lock --check`: pass; `requirements-dev.lock` đã tạo lại bằng `pip-compile`.
- Wheel `uav_crop_analysis-0.1.0-py3-none-any.whl`: build và mở shell từ thư mục cài tạm thành công.
- PyInstaller macOS arm64: bundle shell 154 MB; executable sống qua smoke window và tạo SQLite database.
- Screenshot: chín tổ hợp Overview ở 1366x768, 1440x900, 1920x1080 với scale 100/125/150%; thêm Mission list 1440x900@125%.
- Pixel check: đúng kích thước, ảnh không blank và sidebar render ở cả chín tổ hợp.

Ảnh review nằm trong `docs/phase5/screenshots/`; script tái tạo và kiểm tra là `tools/capture_phase5_ui.py` và `tools/verify_phase5_screenshots.py`.
