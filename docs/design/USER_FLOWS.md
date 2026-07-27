# Desktop User Flows

## Mở mission và chuẩn bị phân tích

1. Người dùng mở màn `Nhiệm vụ`; danh sách được sắp xếp mới nhất trước.
2. Chọn một hàng để mở `Overview` và xem trạng thái dữ liệu của ba drone.
3. Chọn `Dữ liệu` để so sánh ba drone, `Phân tích` cho từng ảnh hoặc `Không gian`
   để tạo/nhập orthomosaic và heatmap.

## Nhập mission

1. Chọn `Nhập mission` và mở manifest JSON.
2. UI giữ phản hồi trong khi thread nền đọc EXIF, telemetry và checksum.
3. Mission hợp lệ xuất hiện trong danh sách; import lỗi hiển thị tổng và không persist
   bundle chưa hoàn chỉnh.

## Phân tích và xem kết quả

1. Chọn task `Cỏ dại · Semantic`, model và checkpoint khả dụng.
2. Chạy job, theo dõi stage/progress; có thể hủy hoặc chạy lại job terminal lỗi.
3. Chọn job hoàn thành và `Mở kết quả`; chuyển original/mask/probability/overlay.

Tab `Ngô · Instance` hiển thị model inventory nhưng khóa lệnh chạy tới khi checkpoint
instance và worker tương ứng được đăng ký.

## Kiểm tra chất lượng dữ liệu

1. Tìm mission theo tên, ID, thời gian hoặc trạng thái.
2. Mở Overview.
3. So sánh số ảnh, GPS ảnh, độ cao và telemetry giữa ba drone.

Trạng thái:

- `Sẵn sàng`: cả ba drone có ảnh và mọi ảnh có GPS cùng độ cao.
- `Thiếu dữ liệu`: thiếu ảnh của ít nhất một drone hoặc metadata ảnh chưa phủ đủ.
- `Chưa có ảnh`: mission đã tồn tại nhưng chưa nhập image asset.

Mission thiếu metadata vẫn có thể chuyển tới cấu hình phân tích ảnh; kết quả không được coi là heatmap địa lý chính xác cho tới khi Phase 7 kiểm tra georeference.

## Orthomosaic và heatmap

1. Mở `Không gian`; kiểm tra số ảnh có GPS/độ cao của cả ba drone.
2. Tạo preview theo ba làn để kiểm tra sequence, hoặc nhập GeoTIFF/chạy NodeODM.
3. Chọn orthomosaic có CRS, model semantic và checkpoint rồi chạy phân tích.
4. Khi job hoàn thành, xuất heatmap; xem CRS, bounds, resolution và provenance ngay trên UI.

Preview luôn hiển thị `KHÔNG GEOREFERENCE`; command phân tích orthomosaic không bật khi
đang chọn preview. NodeODM không bật khi ảnh thiếu GPS hoặc endpoint chưa cấu hình.

## Dashboard và xuất báo cáo

1. Mở `Báo cáo` từ Overview hoặc sidebar.
2. Kiểm tra KPI mission, đúng ba dòng drone, chất lượng từng ảnh, job/model version,
   camera/GSD, spatial product và giới hạn kết quả.
3. Chọn `Xuất báo cáo` và một thư mục đích; tác vụ chạy nền.
4. Sau khi hoàn thành, chọn `Mở HTML` hoặc mở `images.csv`/`report.json` bằng công cụ ngoài.

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
