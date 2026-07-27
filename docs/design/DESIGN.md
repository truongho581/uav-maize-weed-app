# UAV Crop Analysis - Design System

## Mục tiêu

Giao diện là công cụ vận hành cho nhiệm vụ khảo sát nông nghiệp bằng ba drone. Ưu tiên đọc nhanh trạng thái, so sánh dữ liệu theo drone và thực hiện lệnh với số bước ngắn. Giao diện không dùng bố cục landing page, trang trí dư thừa hoặc card lồng card.

## Kiến trúc trình bày

```text
Qt Widgets View -> Qt Model -> Workspace viewmodels
                              -> Application services/ports
                              -> Repository, model catalog, job controller
```

- View chỉ nhận sự kiện, hiển thị state và phát command.
- Viewmodel không import Qt, vì vậy có thể dùng lại khi nhúng module vào phần mềm điều khiển drone.
- `QAbstractTableModel` giữ ID ổn định qua custom role; view không đọc trực tiếp SQLite.
- Job chạy nền không được cập nhật widget từ worker process. UI đọc state đã được parent process lưu.

## Visual Tokens

- Canvas: `#F4F6F5`; surface: `#FFFFFF`; line: `#D9DFDB`.
- Brand/action: `#16724A`; information: `#236C8E`; warning: `#A35C00`; error: `#B13A32`.
- Sidebar: `#18211D`. Màu trạng thái luôn đi cùng chữ, không truyền nghĩa chỉ bằng màu.
- Font fallback: Inter, Segoe UI, SF Pro Text, Noto Sans, Arial; base 10 pt.
- Khoảng cách chính: 8, 12, 18, 24, 32 px. Border radius tối đa 5 px.
- Nút icon dùng `QStyle.StandardPixmap`; icon lạ phải có tooltip và accessible name.

## Component States

| Thành phần | Trạng thái bắt buộc |
| --- | --- |
| Mission list | loading-ready, empty, data, error, filtered-empty |
| Mission row | default, hover, selected, keyboard focus |
| Overview | ready, incomplete metadata, no images, load error |
| Data workspace | ba drone tabs, valid/issue filter, empty/error |
| Analysis command | enabled khi có ảnh/model; disabled kèm trạng thái nguyên nhân |
| Result viewer | original, weed mask, probability, overlay, artifact error |
| Job row | queued, running, cancel requested, cancelled, failed, completed |
| Job error | thông báo ngắn trong trạng thái; chi tiết qua tooltip/inspector |
| Spatial workspace | preview-only, orthomosaic, heatmap, busy/progress, raster error |
| Report workspace | mission summary, three-drone table, image/job tabs, export/open/error |

`loading-ready` hiện đồng bộ vì SQLite local. Khi query chuyển sang IPC/network, state loading phải được thêm mà không đổi contract dữ liệu.

## Bố cục

- Sidebar cố định 220 px; vùng nội dung co giãn từ 804 px trở lên.
- Mission list là bảng dày vừa phải, row 48 px, tên mission là cột co giãn.
- Overview dùng các dải không khung: header, metrics, cấu hình bay, bảng ba drone, job gần đây.
- Bảng drone có chiều cao ổn định cho đúng ba hàng; nội dung động không làm nhảy layout.
- Nút `Phân tích` mở cấu hình model và tạo persisted job; host vẫn nhận được
  `analysisRequested(mission_id)` để tích hợp nếu cần.
- Analysis controls dùng hai hàng để giữ chiều rộng tối thiểu; result toolbar cũng tách
  chọn layer và zoom/opacity để text không bị cắt.
- Spatial product table giữ nhãn độ chính xác bằng chữ; raster viewer đi cùng inspector
  CRS/bounds/resolution/provenance. Preview-only dùng cảnh báo rõ, không mô phỏng bản đồ.
- Report dashboard dùng KPI dạng dải, bảng ba drone cố định và inspector cuộn ở viewport
  thấp. Model chi tiết nằm trong tab Job AI và tooltip ảnh, tránh lặp cột làm vỡ bảng.

## Accessibility

- `Ctrl/Cmd+R`: làm mới; `Ctrl/Cmd+F`: tìm kiếm; `Alt+Left`: quay lại.
- Thứ tự tab đi từ navigation, tìm kiếm, refresh, bảng, rồi command chính.
- Nút chỉ có icon phải có tooltip và accessible name.
- Text tiếng Việt phải vừa ở scale 100%, 125%, 150%; không scale font theo viewport.
- Focus dùng viền xanh thông tin, không chỉ đổi màu nền.

## Nguồn tham khảo

- [Qt for Python](https://doc.qt.io/qtforpython-6/) và [Qt Model/View Programming](https://doc.qt.io/qtforpython-6/overviews/qtwidgets-model-view-programming.html): binding chính thức và tách model/view.
- [QGroundControl](https://github.com/mavlink/qgroundcontrol): tham khảo mật độ thông tin và navigation của trạm điều khiển UAV, không sao chép giao diện.
- [napari](https://github.com/napari/napari): tham khảo workspace ảnh/layer cho Phase 6.
- [Magentic-UI](https://github.com/microsoft/magentic-ui): tham khảo tính minh bạch, khả năng theo dõi và kiểm soát tác vụ dài; áp dụng cho job queue thay vì chat UI.
- [A2UI](https://github.com/a2ui-project/a2ui): tham khảo nguyên tắc dữ liệu khai báo tách khỏi renderer; dự án giữ viewmodel độc lập Qt để dễ nhúng host.

Các repository trên chỉ là nguồn nguyên tắc. UAV Crop Analysis vẫn dùng Qt Widgets và component nội bộ để giảm dependency và giữ trải nghiệm desktop nhất quán.
