# Cải tiến trải nghiệm người dùng

## Mục đích

Tài liệu này là backlog UX cho UAV Crop Analysis. Mục tiêu là giảm thời gian từ lúc
nhận dữ liệu sau chuyến bay đến khi người vận hành có một báo cáo hoặc heatmap đáng tin
cậy, mà không che giấu các điều kiện dữ liệu và giới hạn khoa học của kết quả.

Đối tượng chính là kỹ thuật viên khảo sát nông nghiệp: họ cần biết ngay mission có đủ
ba drone hay chưa, dữ liệu nào cần sửa, phân tích nào đang chạy và kết quả nào đủ điều
kiện dùng cho kiểm tra hoặc lập vùng phun.

## Nguyên tắc quyết định

1. **Hiển thị bước tiếp theo.** Trạng thái bị khóa phải nói rõ điều kiện còn thiếu và
   đưa người dùng tới đúng màn hình để xử lý.
2. **Không suy diễn vị trí.** Preview, ảnh đơn lẻ và dữ liệu mô phỏng không được có
   hình thức khiến người dùng hiểu là bản đồ địa lý đủ điều kiện phun.
3. **Ba drone là đơn vị mặc định.** Các chỉ số quan trọng luôn cho phép so sánh ba lane,
   không buộc người dùng tự tổng hợp từ ba màn hình riêng.
4. **Dễ phục hồi.** Import lỗi, job lỗi và thiếu model phải có nguyên nhân, file/ảnh
   liên quan, hành động sửa và khả năng chạy lại không cần làm lại toàn bộ mission.
5. **Giữ truy vết.** Model, artifact, threshold, nguồn ảnh, telemetry và CRS phải đi
   cùng kết quả xuất để người dùng giải thích được kết quả sau này.

## Backlog ưu tiên P0

### 1. Checklist sẵn sàng theo mission

**Vấn đề hiện tại:** Navigation được khóa khi chưa chọn mission, nhưng người dùng mới
có thể chưa hiểu cần hoàn thành những bước nào trước khi chạy AI hoặc xuất heatmap.

**Cải tiến:** Thêm dải `Sẵn sàng nhiệm vụ` ở Overview, gồm các mục có trạng thái và
liên kết thao tác:

- Đúng 3 drone và mỗi drone có ảnh.
- Timestamp hợp lệ và thứ tự ảnh không lỗi.
- GPS/độ cao đủ cho sản phẩm không gian.
- Camera profile có kích thước/FOV.
- Semantic production checkpoint sẵn sàng.
- Orthomosaic có CRS/transform, chỉ bắt buộc khi xuất heatmap địa lý.

**Tiêu chí hoàn thành:** Mỗi trạng thái chưa đạt có lý do ngắn, số lượng ảnh ảnh hưởng
và nút mở đúng Data/Analysis/Spatial workspace. Không dùng chỉ màu để biểu diễn.

### 2. Kết quả import có thể sửa được

**Vấn đề hiện tại:** Import đã trả lỗi/cảnh báo nhưng thông tin tập trung ở dialog và
không đủ thuận tiện để sửa nhiều file hoặc lặp lại import.

**Cải tiến:** Tạo `Import review` sau khi chọn `mission.json`:

- Tổng hợp số ảnh hợp lệ/lỗi theo từng drone.
- Bảng lỗi có code, tên ảnh, nguyên nhân, mức độ và đường dẫn nguồn.
- Bộ lọc theo drone, lỗi/cảnh báo và loại metadata.
- Nút mở thư mục nguồn/copy lỗi để chỉnh `flight.csv` hoặc ảnh.
- Lưu lịch sử lần import với thời điểm, manifest checksum và kết quả.

**Tiêu chí hoàn thành:** Người dùng xác định được ảnh hay dòng telemetry cần sửa trong
tối đa hai thao tác từ summary; import không hợp lệ không ghi đè mission tốt trước đó.

### 3. Hành động chính của semantic weed

**Vấn đề hiện tại:** Người dùng phải tự chọn model, artifact, tile và overlap dù phần
lớn phiên làm việc dùng SegFormer production mặc định.

**Cải tiến:** Đưa `Phân tích cỏ dại` thành hành động chính trên Overview với preset
`Production (khuyến nghị)`. Khi mở chi tiết vẫn cho thay model/artifact, thiết bị,
tile, overlap và threshold.

Preset phải hiển thị rõ:

- `segformer-b0-v72-production` và `best_fixed_seed_42`.
- Thiết bị đang chọn và cảnh báo khi CUDA không khả dụng.
- Ước tính số ảnh/tile cần chạy, không cam kết thời gian nếu chưa benchmark máy.
- Threshold đang dùng và ảnh hưởng của nó tới weed mask/heatmap.

**Tiêu chí hoàn thành:** Từ mission đã sẵn sàng, người dùng tạo được job semantic bằng
một lệnh; mọi giá trị mặc định vẫn được ghi vào provenance của job.

### 4. Theo dõi job theo ngữ cảnh dữ liệu

**Vấn đề hiện tại:** Job queue có tiến độ nhưng khó biết nó đang xử lý drone nào, ảnh
nào, có thể hủy ở đâu và job nào là kết quả đang được dùng cho báo cáo/heatmap.

**Cải tiến:** Bổ sung inspector job với:

- Stage hiện tại, tiến độ, số ảnh hoàn thành/tổng và ảnh đang xử lý.
- Liên kết tới kết quả hoặc ảnh lỗi, cùng model/artifact/threshold.
- Nhãn `được dùng bởi heatmap` và `được dùng bởi báo cáo`.
- Hành động hủy, chạy lại và sao chép chi tiết lỗi ở vị trí cố định.

**Tiêu chí hoàn thành:** Khi job lỗi, người dùng biết lỗi ở input/model/worker hay
export; khi chạy lại chỉ tạo job mới có provenance riêng, không sửa kết quả cũ.

### 5. Phân biệt rõ preview, orthomosaic và heatmap

**Vấn đề hiện tại:** Ba loại sản phẩm đều là hình ảnh, dễ khiến người dùng nhầm preview
ba lane là dữ liệu có tọa độ hoặc cho rằng heatmap từ ảnh đơn lẻ có thể chỉ vị trí phun.

**Cải tiến:** Chuẩn hóa nhãn, icon và inspector cho từng loại:

| Sản phẩm | Nhãn trạng thái | Lệnh được phép |
| --- | --- | --- |
| Preview ba lane | `Chỉ kiểm tra thứ tự, không có tọa độ` | Xem sequence, không xuất GeoJSON |
| Orthomosaic GeoTIFF | `Có CRS và transform` | Chạy semantic raster, xuất heatmap |
| Weed heatmap | `Có tọa độ theo orthomosaic nguồn` | Xem, xuất GeoTIFF/GeoJSON/PNG |

**Tiêu chí hoàn thành:** Không có đường thao tác nào xuất GeoJSON từ preview hoặc job
không chạy trên orthomosaic. UI hiển thị CRS, bounds, resolution và source job trước
khi người dùng xuất heatmap.

## Backlog ưu tiên P1

### 6. So sánh chất lượng ba lane trên một màn hình

Thêm bảng hoặc strip view đồng bộ ba drone theo `sequence_index`: số ảnh, ảnh thiếu,
GPS, độ cao, timestamp gap, telemetry skew và thumbnail ảnh. Người vận hành nhìn thấy
ngay lane nào thiếu dữ liệu thay vì mở lần lượt ba tab.

**Tiêu chí hoàn thành:** Có thể chọn một lane/ảnh bất thường và mở đúng ảnh nguồn hoặc
dòng telemetry tương ứng.

### 7. Hỗ trợ ảnh lớn và xem kết quả nhanh hơn

Result viewer nên có thumbnail navigator, fit-to-view mặc định, hiển thị tọa độ pixel
và khả năng chuyển ảnh trước/sau trong cùng job. Với ảnh lớn, cần cache thumbnail và
chỉ nạp lớp đang xem để tránh cảm giác ứng dụng bị treo.

**Tiêu chí hoàn thành:** Chuyển giữa ảnh/layer không làm thay đổi kích thước layout;
lỗi artifact vẫn hiển thị ảnh nguồn và cách phục hồi.

### 8. Báo cáo bắt đầu từ câu hỏi vận hành

Trước bảng chi tiết, báo cáo cần trả lời ba câu: `Mission có đủ dữ liệu không?`, `Cỏ
dại tập trung ở đâu?`, `Kết quả nào còn giới hạn?`. Thêm `readiness`, thumbnail
heatmap, số vùng vượt ngưỡng và nguồn tọa độ. Giữ CSV/JSON đầy đủ cho người dùng kỹ
thuật, nhưng HTML ưu tiên tóm tắt có thể in.

**Tiêu chí hoàn thành:** Báo cáo không để trống ý nghĩa khi chưa có heatmap; thay vào
đó nêu điều kiện còn thiếu, ví dụ chưa có orthomosaic hoặc job chưa hoàn thành.

### 9. Preset thu nhận và camera profile

Thêm thư viện preset cho DJI Mini 4K, C12 và camera đã hiệu chuẩn. Preset gồm độ phân
giải, focal/FOV, distortion/calibration reference, độ cao, overlap, gimbal và capture
mode. Cho phép clone rồi khóa cấu hình của một mission đã bắt đầu.

**Tiêu chí hoàn thành:** Camera profile sai kích thước hoặc FOV thiếu được báo ngay
trước import; preset quảng cáo không được đánh dấu là camera calibration đã xác minh.

### 10. Chế độ demo/mô phỏng minh bạch

Mission tạo từ orthomosaic crop cần badge `Dữ liệu mô phỏng`, link đến
`simulation_manifest.json` và chặn xuất kết quả như bằng chứng thực địa nếu chưa được
người dùng xác nhận. Đây là cách demo luồng phần mềm mà không làm lẫn với dữ liệu bay.

**Tiêu chí hoàn thành:** Mọi báo cáo từ mission mô phỏng có watermark/section nêu rõ
nguồn synthetic và các giả định GPS/orthomosaic.

## Backlog ưu tiên P2

### 11. Hướng dẫn thao tác trong ngữ cảnh

Thêm help panel gọn có thể đóng ở từng workspace, chỉ hiển thị điều kiện và bước kế
tiếp của trạng thái hiện tại. Không dùng tutorial che toàn màn hình; link đến
[Hướng dẫn sử dụng](HUONG_DAN_SU_DUNG.md) khi cần nội dung đầy đủ.

### 12. Lưu workspace và thiết lập cá nhân

Lưu mission gần đây, kích thước cột, layer cuối xem, thư mục xuất gần nhất, thiết bị
AI và preset threshold. Các giá trị này cần hiện rõ, có nút reset và không ghi đè
flight profile/provenance của mission.

### 13. Khả năng tiếp cận và mật độ thông tin

Kiểm tra lại desktop ở scale 100%, 125% và 150%; hoàn thiện tooltip/accessible name
cho mọi icon; đảm bảo bảng hỗ trợ keyboard, sort, copy cell và tìm kiếm. Màu xanh/vàng/
đỏ luôn đi kèm text hoặc icon trạng thái.

## Đo lường sau khi triển khai

Theo dõi cục bộ, không gửi dữ liệu ảnh hay GPS ra ngoài mặc định:

- Thời gian từ mở app đến job semantic đầu tiên hoàn thành.
- Số lần import thất bại theo từng error code.
- Tỷ lệ mission có đủ GPS/độ cao và có orthomosaic hợp lệ.
- Tỷ lệ job bị hủy/chạy lại cùng error code.
- Tỷ lệ report có heatmap địa lý so với report chỉ có dữ liệu ảnh.

Các số này dùng để quyết định backlog tiếp theo, không dùng để đánh giá người vận
hành.

## Đã triển khai ngày 29/07/2026

- Chuẩn hóa navigation thành `Dữ liệu`, `Xử lý`, `Bản đồ`, `Báo cáo`.
- Thay các nhãn trộn ngôn ngữ bằng `Tác vụ`, `Trọng số mô hình`, `Độ chồng phủ`,
  `Mặt nạ cỏ dại`, `Chồng lớp`, `Ảnh ghép có tọa độ` và `Bản đồ mật độ cỏ dại`.
- Chuyển các tham số mô hình ít dùng vào dialog thiết lập; vùng viewer được ưu tiên
  diện tích và hàng đợi được giữ ở một cột gọn.
- Tái bố cục bản đồ thành ba vùng; thêm kéo, zoom con lăn, vừa khung, hướng Bắc, tọa
  độ con trỏ, thước tỷ lệ và độ trong suốt.
- Thay icon hệ điều hành của Qt bằng Lucide; các thao tác zoom, vừa khung, thiết lập,
  mở, chạy lại và xóa dùng nút vuông icon-only kèm tooltip.
- Kiểm tra screenshot ở 1440x900 và 1180x720; toolbar không còn chồng chữ hoặc che nút.

## Thứ tự triển khai đề xuất

1. Checklist sẵn sàng mission và import review.
2. Semantic production preset và job inspector.
3. Phân biệt sản phẩm không gian cùng gate xuất heatmap.
4. So sánh ba lane và tối ưu result viewer.
5. Báo cáo định hướng vận hành, camera preset và dấu hiệu dữ liệu mô phỏng.
6. Thiết lập cá nhân, accessibility và đo lường UX.
