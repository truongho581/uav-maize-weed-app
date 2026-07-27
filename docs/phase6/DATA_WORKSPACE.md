# Phase 6 - Data workspace

## Mục đích

Data workspace là điểm kiểm tra dữ liệu trước inference. Một mission luôn gồm đúng ba
drone theo thứ tự làn bay; ảnh không được trộn thành một danh sách ngẫu nhiên.

## Luồng nhập

1. Chọn `Nhập mission` trên màn Nhiệm vụ và mở `mission.json` schema v1.
2. Import chạy trong QThread, đọc EXIF, flight log CSV, checksum và đồng bộ timestamp.
3. Mission chỉ được persist khi không còn lỗi mức `error`; cảnh báo vẫn được lưu cùng
   báo cáo import.
4. Mở `Dữ liệu` để kiểm tra riêng từng drone trước khi chạy AI.

Layout thư mục thực tế không bị hard-code trong UI. Manifest ánh xạ ba `drone_id` tới
thư mục ảnh, telemetry CSV và camera profile. Khi layout dữ liệu thật được cung cấp,
adapter nguồn mới có thể tạo cùng `MissionImportRequest` mà không đổi service/UI.

## Dữ liệu hiển thị

- Ba tab drone theo `lane_index`, số ảnh, telemetry và số lỗi.
- Thời gian chụp, kích thước, GPS, độ cao, độ lệch telemetry và trạng thái từng ảnh.
- Bộ lọc `Chỉ ảnh có lỗi` và bảng lỗi tập trung.
- Camera profile gồm độ phân giải, tiêu cự và các thông số hiệu chuẩn nếu manifest có.

Các kiểm tra hiện có: tệp nguồn mất, thiếu GPS, thiếu độ cao tương đối và độ lệch
telemetry trên 2 giây. Heading, GSD, coverage overlap và camera calibration quality sẽ
được mở rộng cùng geospatial pipeline.

## Điều kiện heatmap

Data workspace không tạo heatmap. Thiếu GPS hoặc georeference không ngăn semantic
inference từng ảnh, nhưng kết quả không được gọi là heatmap địa lý. Phase 7 chịu trách
nhiệm orthomosaic, CRS/transform, projection prediction và quality layer.
