# Phase 9.5.5 - Nhận diện, sidebar và trợ giúp GreenEye

## Nhận diện hiển thị

Tên sản phẩm hiển thị là **GreenEye**. Cửa sổ, application display name, sidebar, tài liệu
người dùng và icon ứng dụng dùng cùng tên và biểu tượng mắt. Package Python, lệnh CLI và
REST contract không đổi để giữ tương thích tích hợp.

## Tương thích dữ liệu cũ

`QApplication.applicationName` tiếp tục là `UAV Crop Analysis` và organization tiếp tục là
`UAV Research Group`. Đây là chủ ý tương thích, không phải tên hiển thị.

Các đường dẫn dữ liệu cũng được giữ nguyên:

- macOS: `~/Library/Application Support/UAV Crop Analysis`.
- Windows: `%LOCALAPPDATA%/UAV Crop Analysis` và `%APPDATA%/UAV Crop Analysis`.
- Linux: các thư mục XDG `uav-crop-analysis` hiện có.

Vì namespace và đường dẫn không đổi, bản nâng cấp nhìn thấy lại mission, camera profile,
job, spatial product, model setting, map key và UI preference cũ. Phase này không sao chép,
đổi tên hay xóa thư mục người dùng.

## Sidebar

Sidebar có hai trạng thái:

- Thu gọn: rộng 56 px, chỉ hiển thị icon; tooltip và accessible name giữ đầy đủ tên.
- Mở rộng: rộng 212 px, hiển thị logo GreenEye, tên màn hình, Trợ giúp và Thu gọn.

Nút mũi tên ở cuối sidebar đổi trạng thái. Giá trị được lưu ngay tại
`ui/sidebar_expanded` trong QSettings và được khôi phục khi mở cửa sổ mới. Mặc định là thu
gọn để dành diện tích cho viewer.

Navigation vẫn dùng một button group độc quyền. Trợ giúp và nút mở rộng không tham gia
group, vì vậy không làm thay đổi màn hình đang chọn.

## Trợ giúp có version

`InfoButton` mở dialog không khóa cửa sổ chính. Nội dung được chọn tại thời điểm bấm theo
workspace hiện tại:

- Nhiệm vụ và Tổng quan.
- Kiểm tra mô hình AI.
- Lập nhiệm vụ bay.
- Dữ liệu/camera, Xử lý ảnh, Bản đồ và Báo cáo.

Mỗi nội dung có khóa, tiêu đề, phần giải thích và `HELP_CONTENT_VERSION`. Dialog luôn hiển
thị cả phiên bản nội dung lẫn phiên bản GreenEye để tài liệu hỗ trợ có thể truy vết. Phím
trợ giúp chuẩn của hệ điều hành mở cùng dialog.

Nội dung AI nêu rõ semantic phân vùng ngô-cỏ, cỏ dại là mục tiêu chính và instance chỉ áp
dụng cho ngô. Nội dung lập nhiệm vụ nhắc rõ GreenEye không kích hoạt động cơ, cất cánh,
tải tệp lên thiết bị hoặc điều khiển drone.

## Khả năng truy cập và responsive

- Mọi nút chỉ có icon có tooltip và accessible name.
- Nút sidebar dùng focus border tương phản trên nền tối.
- Khi mở rộng ở 1180x760, sidebar không che workspace; bảng tiếp tục dùng scroll/elide khi
  chiều rộng giảm.
- Trạng thái mở rộng chỉ ảnh hưởng presentation, không thay đổi mission hoặc provenance.

