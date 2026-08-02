# Hướng dẫn sử dụng GreenEye

## 1. Mục đích và phạm vi

GreenEye quản lý dữ liệu khảo sát của **một đến ba drone**, kiểm tra dữ liệu
ảnh/telemetry, phân vùng ngô - cỏ bằng AI và xuất sản phẩm không gian, heatmap cùng báo
cáo nhiệm vụ. Phần mềm là mô-đun xử lý sau chuyến bay; không thay thế ứng dụng điều
khiển bay hoặc gửi lệnh bay thời gian thực.

Tại phiên bản hiện tại:

- Ngô và cỏ dại dùng **semantic segmentation** bằng
  `segformer-b0-v72-maizemask-weedsgalore`; cỏ dại vẫn là mục tiêu nghiệp vụ chính.
- Ngô chỉ dùng **instance segmentation** bằng `yolov8-seg-v72-instance`, xuất từng
  mask, bounding box và số cây theo `maize2`, `maize4`, `maize6`. Weed không bao giờ
  được suy diễn từ instance model.
- Preview các lane dùng để kiểm tra thứ tự ảnh, **không phải orthomosaic địa lý**.
- Heatmap có tọa độ chỉ được xuất sau khi có orthomosaic GeoTIFF hợp lệ.

## 2. Điều kiện trước khi dùng

### 2.1. Dữ liệu nhiệm vụ

Khi tạo đường bay trong GreenEye, phần mềm xuất sẵn một thư mục mission. Sau chuyến bay,
chép ảnh về đúng thư mục drone; ứng dụng sẽ tự nhận media khi mở lại. Ảnh cần có EXIF
timestamp; GPS và độ cao có thể lấy từ EXIF hoặc telemetry CSV:

```text
GreenEye mission/
  <mission-id>/
  mission.json
  media/
    drone-01/DJI_0001.JPG
    drone-01/telemetry.csv       # tuỳ chọn
    drone-02/DJI_0001.JPG
    drone-03/DJI_0001.JPG
```

Tên `drone-01`, `drone-02` phải đúng với tên thư mục GreenEye đã tạo. Khi cần nhập một
mission cũ theo manifest, vẫn có thể dùng nút **Nhập nhiệm vụ** và
[mission.example.json](phase2/mission.example.json).

Khuyến nghị bay: độ cao 10-20 m, gimbal nadir `-90`, dừng ổn định để chụp, forward
overlap 70-80% và side overlap 60-70%. Không trộn ảnh không rõ drone hoặc ảnh từ các
chuyến bay khác nhau vào cùng mission.

### 2.2. Model pack

Checkpoint production nằm tại `models/checkpoints/` và bị Git ignore. Registry
`models/model_inventory.json` phải còn nguyên để ứng dụng xác minh checksum trước khi
nạp model. Thông tin bộ trọng số tại [PRODUCTION_MODEL_PACK.md](phase9/PRODUCTION_MODEL_PACK.md).

### 2.3. Chạy ứng dụng

Từ source project:

```bash
.venv/bin/uav-crop-analysis
```

Hoặc dùng bundle macOS đã build:

```bash
./dist/UAV_CropAnalysis/UAV_CropAnalysis
```

Muốn tạo orthomosaic tự động, chỉ cần cài Docker Desktop. App sẽ thử mở Docker Desktop
khi daemon chưa chạy; không cần build hoặc chạy NodeODM bằng terminal:

```bash
.venv/bin/uav-crop-analysis
```

## 3. Quy trình thao tác trên desktop

### Bước 1: Tạo hoặc nhận mission

1. Mở màn hình **Nhiệm vụ**, tạo mission và lập đường bay.
2. Xuất nhiệm vụ một lần. GreenEye ghi nhớ thư viện `GreenEye mission/` đã chọn.
3. Sau khi bay, chép ảnh vào `media/<drone-id>/` của mission tương ứng.
4. Mở lại ứng dụng. Media hợp lệ được tự nhận, kiểm tra và hiển thị trạng thái nhiệm vụ.
5. Với dữ liệu cũ không theo cấu trúc này, chọn **Nhập nhiệm vụ** và tệp manifest JSON.

Importer kiểm tra ảnh trùng, thiếu ảnh, timestamp, GPS, độ cao và độ lệch telemetry.
Mission chỉ được lưu khi không có lỗi mức `error`. Các cảnh báo vẫn cần được xem trước
khi chạy AI.

Khi chưa chọn mission, các màn hình **Dữ liệu**, **Xử lý ảnh**, **Bản đồ** và
**Báo cáo** bị khóa. Màn **Kiểm tra mô hình** luôn dùng được vì hoạt động độc lập.

Sidebar mặc định chỉ hiển thị biểu tượng. Dùng nút mũi tên ở cuối sidebar để mở tên các
màn hình; lựa chọn này được ghi nhớ cho lần mở ứng dụng sau. Nút **Trợ giúp** hoặc phím
trợ giúp chuẩn của hệ điều hành mở hướng dẫn ngắn theo đúng màn hình đang xem, kèm phiên
bản nội dung và phiên bản GreenEye.

Tên hiển thị mới là GreenEye nhưng ứng dụng tiếp tục dùng thư mục dữ liệu và namespace
thiết lập `UAV Crop Analysis` của các bản trước. Không đổi tên hoặc di chuyển thư mục này
khi nâng cấp, nhờ đó mission, camera, job, bản đồ và khóa bản đồ đã lưu vẫn được nhận lại.

### Kiểm tra model trước khi xử lý mission

1. Chọn biểu tượng máy ảnh **Kiểm tra mô hình** trên sidebar.
2. Chọn **Ngô - cỏ** hoặc **Cây ngô**, sau đó chọn checkpoint cần thử.
3. Chọn một ảnh hoặc video. Video được lấy tối đa 12 khung đại diện trên toàn thời lượng.
4. Chọn **Chạy kiểm tra**, rồi dùng mũi tên trong viewer để xem từng ảnh hoặc khung.
5. Bật lớp phân vùng, mặt nạ, xác suất hoặc chồng lớp để đánh giá trực quan.

Kết quả kiểm tra tách biệt với mission và không được đưa vào hàng đợi xử lý chính.

### Bước 2: Kiểm tra dữ liệu theo drone

1. Trong trang tổng quan mission, chọn **Dữ liệu**.
2. Xem từng tab drone để kiểm tra số ảnh, thứ tự chụp, GPS, độ cao và lỗi.
3. Sửa dữ liệu nguồn hoặc telemetry rồi nhập lại mission nếu có các lỗi như
   `missing_gps`, `missing_relative_altitude`, `duplicate_image` hoặc ảnh thiếu.

Mục tiêu trước khi phân tích là mọi lane đã khai báo đều có ảnh hợp lệ, GPS coverage
và altitude coverage đạt 100% khi cần sản phẩm không gian.

### Bước 3: Chạy phân vùng ngô - cỏ

1. Chọn **Xử lý ảnh**.
2. Chọn tab **Phân vùng ngô - cỏ**.
3. Chọn `segformer-b0-v72-maizemask-weedsgalore` và artifact
   `best_joint_seed_42`.
4. Chọn thiết bị `cpu` hoặc `cuda` khi máy có PyTorch CUDA phù hợp.
5. Đặt tile size, overlap và ngưỡng cỏ dại, rồi chọn **Chạy phân tích**.
6. Theo dõi trạng thái job; khi hoàn thành, xem bản đồ ba lớp, mask ngô, mask cỏ,
   xác suất cỏ và tỷ lệ diện tích từng lớp trên mỗi ảnh.

Ngưỡng cỏ dại thay đổi lớp mask xuất bản và heatmap sau này. Ghi lại ngưỡng khi so
sánh kết quả giữa các lần chạy.

### Bước 3b: Chạy instance ngô

1. Chọn tab **Đếm cây ngô**.
2. Chọn `yolov8-seg-v72-instance` và artifact `best_fixed_seed_42`.
3. Chọn thiết bị phù hợp, rồi chọn **Chạy phân tích**.
4. Khi hoàn thành, xem **Mask ngô** hoặc **Overlay** để kiểm tra từng cây và tổng số
   theo giai đoạn trong JSON kết quả.

Ảnh lớn được cắt tile có overlap rồi hợp nhất mask trùng ở biên. Ngưỡng weed bị khóa
ở tab này vì không áp dụng cho instance ngô; score và NMS dùng cấu hình checkpoint.
Không dùng mask `crop` từ semantic model để giả kết quả đếm hoặc tách từng cây ngô.

### Bước 4: Kiểm tra preview hoặc tạo orthomosaic

1. Chọn **Bản đồ**, sau đó mở hộp thoại **Nguồn bản đồ** bằng nút thư mục trên thanh
   tiêu đề.
2. Dùng **Tạo ảnh xem nhanh** để xem contact sheet theo lane và sequence.
3. Để có dữ liệu địa lý, dùng một trong hai cách trong hộp thoại:
   - Chọn **Nhập GeoTIFF** và chọn ảnh ghép có CRS cùng affine transform hợp lệ.
   - Chọn **Dựng ảnh ghép**. App tự kiểm tra Docker, tải image ở lần đầu, khởi động
     NodeODM, gửi ảnh và tải orthophoto GeoTIFF.
4. Chọn orthomosaic đã tạo/nhập làm raster nguồn, rồi chạy semantic weed trên chính
   raster đó.

Preview luôn có nhãn `NOT GEOREFERENCED`; không dùng preview để quyết định vị trí phun.
NodeODM từ chối mission thiếu GPS. Ảnh có GPS từ telemetry được gửi kèm `geo.txt`;
orthophoto hoàn tất được tự chọn và mở trong viewer của trang **Bản đồ**.

Panel **Bản đồ thực địa** hiển thị nền ảnh vệ tinh và vẽ footprint orthomosaic thành
polygon theo đúng bốn góc tọa độ của GeoTIFF. Nhấp vào preview nhỏ để mở bản đồ lớn,
kéo/thu phóng và bật hoặc tắt ranh giới, tâm ảnh ghép, orthomosaic hay mật độ cỏ dại.
Ứng dụng ưu tiên Google Maps Hybrid khi đã lưu Maps JavaScript API key; nếu chưa có key,
ứng dụng dùng Esri World Imagery. Nền vệ tinh cần Internet; dữ liệu nhiệm vụ vẫn nằm cục bộ.
Để dùng Google Maps, mở bản đồ lớn, chọn nút thiết lập ở góc trên bên phải và lưu API key
đã bật **Maps JavaScript API** cùng billing. Không đưa key vào source hoặc model pack.

### Bước 5: Xuất heatmap cỏ dại

Sau khi job semantic chạy hoàn tất trên orthomosaic:

1. Trong **Bản đồ**, chọn tác vụ và orthomosaic phù hợp.
2. Đặt ngưỡng cỏ dại.
3. Chọn **Xuất heatmap**.

Gói xuất gồm GeoTIFF probability, GeoTIFF mask, PNG xem nhanh, GeoJSON vùng vượt
ngưỡng và valid-data mask. GeoJSON được chuyển sang `EPSG:4326`, vì vậy có thể đưa vào
QGIS hoặc phần mềm lập vùng phun. Vị trí này chỉ đáng tin ở mức orthomosaic/GPS đầu
vào, không tự động thay thế kiểm tra thực địa hay RTK/GCP.

### Bước 6: Xuất báo cáo

1. Chọn **Báo cáo**.
2. Kiểm tra tổng số ảnh, ảnh hợp lệ, job AI, coverage cỏ dại, camera và sản phẩm
   không gian.
3. Chọn **Xuất báo cáo** và thư mục đầu ra.
4. Dùng **Mở HTML** để xem bản báo cáo tự chứa trong trình duyệt.

Mỗi lần xuất tạo một thư mục gồm `report.json`, `images.csv`, `report.html`,
`manifest.json` và thư mục `maps/`. Báo cáo đặt ảnh ghép GeoTIFF cạnh heatmap cỏ dại;
`maps/` chứa bản sao hai GeoTIFF và manifest ghi SHA-256 cho từng tệp.

## 4. Mission mô phỏng có sẵn trên máy phát triển

Nếu đã tạo dữ liệu mô phỏng từ `DJI_0438.JPG` và `DJI_0438.DNG`, manifest nằm tại:

```text
sample_data/simulated_missions/dji0438_10m_three_drone/mission.json
```

Mission này có 12 crop từ một ảnh orthomosaic-like, ba drone và telemetry tổng hợp từ
metadata DNG. Đây là **dữ liệu mô phỏng**, không phải log bay hay orthomosaic thực
địa. Các giả định vị trí nằm trong `simulation_manifest.json` cùng thư mục.

Tái tạo bộ dữ liệu bằng:

```bash
.venv/bin/python tools/create_simulated_orthomosaic_mission.py \
  /duong-dan/DJI_0438.JPG \
  /duong-dan/DJI_0438.DNG \
  sample_data/simulated_missions/dji0438_10m_three_drone
```

## 5. Dùng CLI

CLI dùng cùng database với desktop khi không truyền `--database`.

```bash
# Xem mission
.venv/bin/uav-crop mission list

# Nhập một mission
.venv/bin/uav-crop mission import /duong-dan/mission.json

# Xem chi tiết một mission
.venv/bin/uav-crop mission show mission-id

# Chạy semantic ngô - cỏ
.venv/bin/uav-crop job submit mission-id \
  --model segformer-b0-v72-maizemask-weedsgalore \
  --artifact best_joint_seed_42 \
  --threshold 0.5

# Xuất báo cáo
.venv/bin/uav-crop report mission-id --output /duong-dan/reports
```

Lệnh `uav-crop capabilities` liệt kê khả năng API và chế độ drone read-only. Dùng
`uav-crop serve --host 127.0.0.1 --port 8765` để mở REST API cục bộ cho hệ thống điều
khiển bên ngoài.

## 6. Xử lý sự cố

| Hiện tượng | Cách xử lý |
| --- | --- |
| Không chọn được Phân tích/Không gian/Báo cáo | Chọn hoặc import một mission ở màn hình Mission trước. |
| Mission không được lưu | Đọc lỗi import; thường là thư mục ảnh thiếu, EXIF timestamp không hợp lệ, GPS/độ cao thiếu hoặc CSV telemetry sai cột. |
| Nút chạy semantic bị khóa | Kiểm tra mission đã chọn, checkpoint ở `models/checkpoints/` và artifact có checksum đúng. |
| Không có heatmap vị trí | Preview không đủ. Nhập GeoTIFF có CRS/transform hoặc chạy NodeODM, sau đó chạy semantic trên orthomosaic. |
| Không chạy được Ngô instance | Kiểm tra `best.pt` tồn tại tại `models/checkpoints/instance/yolov8-seg-v72-instance/`, checksum trong registry đúng và bundle có Ultralytics/OpenCV. Mask R-CNN vẫn chưa có checkpoint nên chưa chạy được. |
| Không tìm thấy Docker | Cài Docker Desktop, mở Docker và chờ daemon sẵn sàng rồi chạy lại NodeODM. |
| Không tải được NodeODM | Kiểm tra mạng ở lần đầu, dung lượng đĩa và quyền chạy Docker. App không yêu cầu `docker build`. |
| Cổng 3000 đang được dùng | Dừng dịch vụ chiếm `127.0.0.1:3000` hoặc container NodeODM cũ không do app quản lý. |
| Kết quả vị trí không khớp thực địa | Kiểm tra GPS, heading, độ cao, camera calibration, CRS và chất lượng orthomosaic; dùng GCP/RTK khi cần độ chính xác cao. |

## 7. Lưu ý vận hành

- Không dùng heatmap từ dữ liệu thiếu GPS để chỉ đạo phun ngoài đồng.
- Không công bố tính năng realtime hoặc điều khiển bay tự động: tích hợp QGC/MAVSDK
  hiện là read-only.
- Luôn giữ riêng dữ liệu của từng drone và lưu `mission.json`, telemetry, ảnh nguồn,
  model ID/artifact role cùng báo cáo để có thể tái lập kết quả.
- Checkpoint và dữ liệu ảnh lớn không được commit Git; sao lưu chúng theo quy trình dữ
  liệu của dự án.
