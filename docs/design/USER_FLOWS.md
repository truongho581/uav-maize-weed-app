# Desktop User Flows

## Mở mission và chuẩn bị phân tích

1. Người dùng mở màn `Nhiệm vụ`; danh sách được sắp xếp mới nhất trước.
2. Chọn một hàng để mở tổng quan và xem trạng thái dữ liệu của các drone đã khai báo.
3. Chọn `Dữ liệu` để so sánh 1-3 drone, `Xử lý` cho từng ảnh hoặc `Bản đồ`
   để tạo/nhập ảnh ghép và bản đồ mật độ cỏ dại.

## Nhập mission

1. Chọn `Nhập nhiệm vụ` và mở tệp mô tả JSON.
2. Giao diện vẫn phản hồi trong khi luồng nền đọc EXIF, hành trình và mã kiểm tra.
3. Nhiệm vụ hợp lệ xuất hiện trong danh sách; dữ liệu lỗi được tổng hợp và bộ dữ liệu
   chưa hoàn chỉnh không được lưu.

## Phân tích và xem kết quả

1. Chọn `Cỏ dại (phân vùng)` hoặc `Cây ngô (đối tượng)` và mô hình khả dụng.
2. Mở `Thiết lập` khi cần đổi trọng số, thiết bị, ô ảnh, chồng phủ hoặc ngưỡng.
3. Chạy tác vụ, theo dõi tiến độ; có thể hủy, xóa hoặc chạy lại tác vụ lỗi.
4. Chọn tác vụ hoàn thành và chuyển giữa ảnh gốc, mặt nạ, xác suất, chồng lớp.

Tab `Cây ngô (đối tượng)` khóa lệnh chạy tới khi trọng số và bộ xử lý tương ứng được
đăng ký.

## Kiểm tra chất lượng dữ liệu

1. Tìm mission theo tên, ID, thời gian hoặc trạng thái.
2. Mở tổng quan.
3. So sánh số ảnh, GPS ảnh, độ cao và mẫu hành trình giữa các drone.

Trạng thái:

- `Sẵn sàng`: mọi drone đã khai báo có ảnh và mọi ảnh có GPS cùng độ cao.
- `Thiếu dữ liệu`: thiếu ảnh của ít nhất một drone hoặc metadata ảnh chưa phủ đủ.
- `Chưa có ảnh`: mission đã tồn tại nhưng chưa nhập image asset.

Mission thiếu metadata vẫn có thể chuyển tới cấu hình phân tích ảnh; kết quả không được coi là heatmap địa lý chính xác cho tới khi Phase 7 kiểm tra georeference.

## Ảnh ghép và bản đồ mật độ

1. Mở `Bản đồ`; kiểm tra số ảnh có GPS/độ cao của mọi drone đã khai báo.
2. Tạo ảnh xem nhanh theo các làn, nhập GeoTIFF hoặc chọn `Dựng ảnh ghép`.
3. Chọn ảnh ghép đã định vị, mở `Thiết lập mô hình` rồi phân tích cỏ dại.
4. Khi tác vụ hoàn thành, tạo bản đồ mật độ; xem hệ tọa độ, phạm vi, độ phân giải
   và nguồn gốc xử lý ngay trên giao diện.

Ảnh xem nhanh luôn hiển thị `không có tọa độ`; lệnh phân tích không bật khi đang chọn
loại ảnh này. NodeODM không bật khi ảnh thiếu GPS; Docker được kiểm tra khi chạy.

## Dashboard và xuất báo cáo

1. Mở `Báo cáo` từ Overview hoặc sidebar.
2. Kiểm tra chỉ số nhiệm vụ, số dòng drone tương ứng, chất lượng từng ảnh, tác vụ/mô hình,
   máy ảnh/GSD, sản phẩm bản đồ và giới hạn kết quả.
3. Chọn `Xuất báo cáo` và một thư mục đích; tác vụ chạy nền.
4. Sau khi hoàn thành, chọn `Mở báo cáo` hoặc mở `images.csv`/`report.json` bằng công cụ ngoài.

Mỗi lần xuất tạo thư mục mới và manifest checksum, không ghi đè report trước.

## Lỗi truy vấn

1. Viewmodel bắt lỗi từ query adapter và chuyển thành error state.
2. UI giữ nguyên process, hiển thị trạng thái lỗi và cho phép `Làm mới`.
3. Chi tiết kỹ thuật được ghi log tại thư mục ứng dụng; không hiển thị traceback trong UI.

## Bàn phím

- `Ctrl/Cmd+F` đưa focus vào tìm kiếm mission.
- `Ctrl/Cmd+R` đọc lại dữ liệu.
- `Alt+Left` quay về Mission list.
- `Tab`, phím mũi tên và `Enter/Space` dùng navigation/command chuẩn Qt.

## Integration Host

Host Python mở public SDK mà không import Qt:

```python
from uav_crop_analysis.sdk import UavCropAnalysis

with UavCropAnalysis.open() as sdk:
    mission = sdk.get_mission("mission-id")
```

Host khác ngôn ngữ gọi REST `/api/v1`; poll `jobs/{id}` và đọc `results`/`report`. Kết nối
drone chỉ dùng `MavsdkReadOnlyAdapter`; không có command gửi về autopilot.
