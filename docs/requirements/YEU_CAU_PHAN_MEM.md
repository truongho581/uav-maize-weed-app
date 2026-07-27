# Yêu cầu phần mềm UAV Crop Analysis

## 1. Căn cứ và phạm vi

Tài liệu này tổng hợp yêu cầu phần mềm từ báo cáo nghiệm thu đề tài **"Nghiên cứu giải pháp áp dụng tổ hợp drone giám sát sinh trưởng của cây trồng nông nghiệp"** và hiện trạng mã nguồn của dự án.

Mục tiêu bàn giao là một mô-đun phần mềm có thể mở rộng, tích hợp mô hình AI và thuật toán xử lý dữ liệu để giám sát sinh trưởng cây trồng từ dữ liệu của tổ hợp **03 drone**. Mô-đun áp dụng cho dữ liệu ghi nhận ở độ cao bay khoảng **10 m đến 20 m**.

Phần mềm là mô-đun phân tích và quản lý dữ liệu nhiệm vụ bay. Nó có thể tích hợp với hệ thống điều khiển trạm mặt đất, nhưng không mặc định phải tự điều khiển động cơ hoặc thay thế phần mềm bay của drone.

## 2. Diễn giải yêu cầu "xử lý điều khiển kết hợp 3 drone"

Yêu cầu này đòi hỏi phần mềm hỗ trợ một nhiệm vụ chung có ba drone hoạt động đồng thời: chia vùng bay, gán drone, theo dõi dữ liệu trả về theo từng drone và tổng hợp thành kết quả cho toàn khu vực.

Báo cáo không nêu chỉ tiêu về độ trễ, video trực tiếp, telemetry liên tục hay giao thức điều khiển. Vì vậy, **xử lý thời gian thực không phải yêu cầu bắt buộc** nếu không được bổ sung trong đặc tả/biên bản nghiệm thu. Tuy nhiên, chỉ nhập một thư mục ảnh ngẫu nhiên rồi phân tích độc lập sẽ không đủ căn cứ để chứng minh khả năng xử lý tổ hợp ba drone hoặc tạo heatmap theo không gian.

## 3. Quy trình nghiệp vụ bắt buộc

```text
Tạo nhiệm vụ -> Chia khu vực cho 3 drone -> Lập đường bay -> Bay/chụp ảnh
-> Thu nhận dữ liệu có định danh -> Kiểm tra dữ liệu -> AI phân tích từng ảnh
-> Ghép theo vị trí -> Heatmap và báo cáo toàn khu vực
```

1. Người vận hành tạo một nhiệm vụ bay (`mission_id`) cho cánh đồng/khu vực cần khảo sát.
2. Hệ thống chia khu vực khảo sát thành ba cụm dải bay liền kề và gán lần lượt cho `drone_01`, `drone_02`, `drone_03`. Ba drone bay song song trên cùng khu vực khảo sát, mỗi drone chỉ hoạt động trong hành lang được giao để tránh giao cắt.
3. Mỗi drone bay theo đường quét kiểu lawnmower/grid, ở độ cao 10-20 m; giữ cùng cấu hình camera khi có thể. Gimbal C12 được khóa nhìn thẳng xuống mặt đất trong suốt nhiệm vụ (pitch danh định `-90°` theo quy ước phổ biến của gimbal). Trong mỗi dải, drone bay một quãng đường xác định, **dừng/hover ổn định để chụp một ảnh**, rồi mới bay tiếp; ưu tiên kích hoạt chụp theo **quãng đường bay** thay vì chỉ theo thời gian.
4. Ảnh liên tiếp trên cùng dải phải có chồng phủ dọc và hai dải kề nhau phải có chồng phủ ngang. Giá trị khởi đầu khuyến nghị là chồng phủ dọc 70-80% và chồng phủ ngang 60-70%, bao gồm cả ranh giới giữa hành lang của hai drone; cần hiệu chỉnh theo camera, độ cao và tốc độ bay thực tế.
5. Dữ liệu sau bay được nhập theo đúng nhiệm vụ và drone, sau đó kiểm tra tính đầy đủ trước khi phân tích.
6. AI nhận dạng cây, giai đoạn sinh trưởng và cỏ dại trên từng ảnh; kết quả được đặt lại đúng vị trí để tạo heatmap, vùng rủi ro và báo cáo tổng hợp.

### 3.1. Quy tắc tính khoảng chụp và khoảng cách dải bay

Gọi `L` là chiều dài và `W` là chiều rộng vùng phủ mặt đất của một ảnh ở độ cao bay hiện tại. Với chồng phủ dọc `O_d` và chồng phủ ngang `O_n` (dạng số thập phân), cấu hình nhiệm vụ cần tuân theo:

```text
Khoảng chụp theo chiều bay = L x (1 - O_d)
Khoảng cách giữa hai dải bay = W x (1 - O_n)
```

Ví dụ, khi cần chồng phủ dọc 75%, ảnh tiếp theo được chụp sau 25% chiều dài vùng phủ mặt đất của ảnh trước. Nếu drone bay với tốc độ `v`, chu kỳ chụp tương đương `khoảng chụp / v`, nhưng kích hoạt theo quãng đường sẽ ổn định hơn khi tốc độ bay thay đổi.

Với quy trình dừng/chụp/bay tiếp, kế hoạch cần thêm thời gian hover tối thiểu sau khi drone đạt waypoint để gimbal và thân drone ổn định; ảnh chỉ được trigger khi trạng thái bay ổn định. Điều này giảm nhòe chuyển động và cải thiện chất lượng ghép ảnh.

## 3.2. Kết quả không gian của nhiệm vụ

Các ảnh có metadata GPS, độ cao, hướng bay và chồng phủ phù hợp được ghép thành **orthomosaic** (ảnh trực giao toàn khu vực). Kết quả AI về ngô và cỏ dại được chiếu lên orthomosaic để tạo heatmap có vị trí thực địa. Việc ghép cần dùng thông tin định vị; ảnh chỉ theo thứ tự tên tệp không đủ để tạo orthomosaic đáng tin cậy.

## 4. Dữ liệu đầu vào

### 4.1. Cấu trúc dữ liệu tối thiểu

```text
missions/
  mission_2026_001/
    mission.json
    drone_01/
      images/
      flight_log.csv
    drone_02/
      images/
      flight_log.csv
    drone_03/
      images/
      flight_log.csv
```

`mission.json` cần có tối thiểu: `mission_id`, thời gian, tên khu vực, loại cây, hệ tọa độ, độ cao kế hoạch và thông tin ba drone/vùng được giao.

Mỗi ảnh cần liên kết được với tối thiểu các trường sau. Góc gimbal không cần lưu theo từng ảnh khi đã khóa cố định góc nhìn thẳng đứng, nhưng phần mềm cần lưu cấu hình gimbal của nhiệm vụ và cảnh báo nếu góc thực tế lệch đáng kể khỏi `-90°`:

| Trường | Bắt buộc | Mục đích |
| --- | --- | --- |
| `mission_id` | Có | Gom dữ liệu đúng một lần khảo sát |
| `drone_id` | Có | Phân biệt dữ liệu của ba drone |
| `image_id` hoặc tên ảnh | Có | Truy vết kết quả AI |
| `captured_at` | Có | Sắp xếp và kiểm tra trình tự ảnh |
| `latitude`, `longitude` hoặc `grid_row`, `grid_col` | Có | Đặt ảnh/kết quả lên bản đồ heatmap |
| `altitude_m` | Khuyến nghị mạnh | Kiểm tra điều kiện 10-20 m và quy đổi diện tích |
| `heading` | Khuyến nghị | Ghép ảnh và kiểm tra đường bay |
| `gsd_cm_per_px` | Khuyến nghị | Quy đổi diện tích/mật độ chính xác |

Ưu tiên đọc GPS, thời gian và độ cao từ EXIF của ảnh. Khi ảnh không có GPS, phần mềm phải cho phép nhập `flight_log.csv` hoặc lưới vị trí (`grid_row`, `grid_col`) để không tạo heatmap từ thứ tự ngẫu nhiên.

### 4.3. Cấu hình camera C12 và hiệu chuẩn

Thông số công bố cho camera ánh sáng nhìn thấy C12: ảnh lưu `2560 x 1440` (JPEG), cảm biến/ống kính được quảng cáo 5 MP, tiêu cự `f=3.5-4.75 mm`, khẩu độ `F2.0`, và góc nhìn `HFOV/VFOV/DFOV = 100°/52°/122°`. Trong một nhiệm vụ phải khóa độ phân giải, góc gimbal và mức zoom số (khuyến nghị `1x`, không zoom số).

Nhà sản xuất không công bố kích thước cảm biến, ma trận nội tại, điểm chính quang hoặc hệ số méo ống kính. Do đó trước khi lập orthomosaic, dự án phải hiệu chuẩn từng cụm camera C12 bằng bảng Charuco/checkerboard, lưu tối thiểu `fx`, `fy`, `cx`, `cy`, `k1`, `k2`, `k3`, `p1`, `p2` và sai số tái chiếu. Không được coi quảng cáo "distortion-free" là dữ liệu hiệu chuẩn quang học.

### 4.2. Điều kiện hợp lệ để tạo heatmap

Heatmap toàn khu vực chỉ được tạo khi từng ảnh có tọa độ địa lý hoặc vị trí lưới rõ ràng. Nếu không thỏa điều kiện này, phần mềm chỉ được xuất heatmap/cảnh báo **trên từng ảnh**, đồng thời phải thông báo rằng không thể suy ra vị trí chính xác ngoài thực địa.

## 5. Chức năng cần có

### 5.1. Quản lý nhiệm vụ ba drone

- Tạo, mở, lưu và xóa nhiệm vụ khảo sát.
- Khai báo ranh giới khu vực, loại cây, thời gian, độ cao bay và cấu hình chụp.
- Chia khu vực hoặc nhập sẵn ba vùng/dải bay; gán rõ một drone cho từng vùng.
- Nhập kế hoạch bay/nhật ký bay từ hệ thống điều khiển bên ngoài khi có.
- Hiển thị trạng thái dữ liệu của từng drone: số ảnh, thiếu ảnh, ảnh trùng, khoảng thời gian và vùng được phủ.

### 5.2. Nhập, kiểm tra và chuẩn hóa dữ liệu

- Nhập ảnh riêng theo từng `drone_id`, không chỉ chọn một thư mục ảnh chung.
- Đọc EXIF hoặc tệp nhật ký để lấy thời gian, GPS, độ cao, hướng bay.
- Sắp xếp ảnh theo thời gian và/hoặc vị trí; phát hiện ảnh thiếu, ảnh trùng, ảnh nằm ngoài nhiệm vụ hoặc sai drone.
- Kiểm tra độ cao dữ liệu và cảnh báo khi nằm ngoài 10-20 m.
- Lưu bản sao metadata chuẩn hóa gắn với từng ảnh và kết quả AI.

### 5.3. Phân tích AI

- Nhận dạng và phân đoạn ngô, cỏ dại từ ảnh UAV.
- **Ngô là đối tượng instance segmentation**: tách từng cây riêng lẻ, đếm số cây, tính diện tích tán/mật độ từng cây và phân loại giai đoạn sinh trưởng khi mô hình có nhãn tương ứng.
- **Cỏ dại là đối tượng semantic segmentation**: tạo mask vùng cỏ dại, tính tỷ lệ che phủ, mật độ che phủ theo ô lưới và vùng cạnh tranh; không yêu cầu đếm từng cá thể cỏ dại.
- Tính các chỉ số theo ảnh: tỷ lệ che phủ ngô, tỷ lệ che phủ cỏ dại, số lượng ngô, mật độ ngô, diện tích tán ngô và vùng cạnh tranh cỏ dại.
- Cho phép cấu hình ngưỡng tin cậy, IoU, GSD và ngưỡng cảnh báo cỏ dại.
- Lưu kết quả theo `mission_id`, `drone_id` và `image_id` để có thể tái lập báo cáo.

### 5.4. Ghép không gian và heatmap

- Ghép kết quả của các ảnh trong cùng drone theo GPS/lưới; sau đó ghép ba vùng của ba drone thành bản đồ chung.
- Hiển thị heatmap cho tối thiểu mật độ cỏ dại hoặc mức độ che phủ cỏ dại; có thang màu, đơn vị và chú giải.
- Hiển thị vùng cảnh báo trên bản đồ để người vận hành biết vị trí cần kiểm tra/xử lý.
- Không dùng phép ghép ảnh thị giác đơn thuần làm cơ sở duy nhất cho vị trí ngoài thực địa; GPS/lưới nhiệm vụ là nguồn định vị chính.
- Gắn mức độ tin cậy hoặc cảnh báo khi vùng ảnh bị thiếu, GPS không hợp lệ hoặc chồng phủ không đủ.

### 5.5. Báo cáo và xuất dữ liệu

- Dashboard tổng hợp cho toàn nhiệm vụ và chi tiết theo từng drone.
- Xuất CSV tối thiểu có `mission_id`, `drone_id`, `image_id`, thời gian, vị trí, chỉ số cây trồng, chỉ số cỏ dại và trạng thái cảnh báo.
- Xuất ảnh heatmap/bản đồ vùng cảnh báo và báo cáo tổng hợp theo nhiệm vụ.
- Báo cáo cần nêu rõ số drone sử dụng, vùng phụ trách, số ảnh hợp lệ, ảnh lỗi/thiếu và phạm vi kết quả.

## 6. Tích hợp điều khiển bay

Mức tối thiểu để đáp ứng đề tài là phần mềm nhận hoặc xuất được kế hoạch/nhiệm vụ cho hệ thống điều khiển drone bên ngoài, đồng thời quản lý dữ liệu theo ba drone. Có thể tích hợp dần với Ground Control Station thông qua tệp kế hoạch bay, tệp nhật ký bay hoặc API phù hợp.

Các khả năng sau là phần mở rộng, chỉ nên công bố là "realtime" khi đã kiểm thử thực tế:

- Nhận telemetry và ảnh khi drone đang bay.
- Cập nhật tiến độ phủ khu vực và heatmap theo từng ảnh/lô ảnh mới nhận.
- Cảnh báo vùng bất thường để điều chỉnh nhiệm vụ trong khi bay.
- Gửi lệnh hoặc cập nhật waypoint trở lại bộ điều khiển bay.

## 7. Đối chiếu với hiện trạng phần mềm

| Hạng mục | Hiện trạng | Cần bổ sung |
| --- | --- | --- |
| AI phát hiện cây/cỏ dại | Đã có | Kiểm thử bằng dữ liệu thực tế ở 10-20 m |
| Xử lý ảnh dung lượng lớn bằng chia tile | Đã có | Giữ lại, bổ sung metadata kết quả |
| Chỉ số cây/cỏ dại theo ảnh | Đã có | Chuẩn hóa đơn vị và độ chính xác GSD |
| Nhập một ảnh/thư mục ảnh | Đã có | Nhập theo `mission_id` và `drone_id` |
| Ghép ảnh trực quan | Có ở mức thử nghiệm | Chuyển sang ghép theo GPS/lưới nhiệm vụ |
| Heatmap cỏ dại | Có theo ảnh | Heatmap địa lý/toàn khu vực 3 drone |
| Quản lý ba drone | Đã có | Mission đúng ba drone, lane và mapping system ID |
| Kế hoạch/quy trình bay | Có ở Phase 9 | Đọc QGC Plan/survey polygon và QGC CSV/tlog; chưa gửi mission |
| Báo cáo theo nhiệm vụ/drone | Đã có ở Phase 8 | Dashboard, JSON/CSV/HTML versioned và liên kết bản đồ |
| Điều khiển/giám sát realtime | Read-only thử nghiệm | MAVSDK telemetry/mission và reconnect; chưa kiểm thử thiết bị, không gửi lệnh |

## 8. Tiêu chí nghiệm thu đề xuất

1. Phần mềm tạo được một nhiệm vụ gồm đúng ba drone và gán được vùng/dải bay cho từng drone.
2. Phần mềm nhập được ba bộ ảnh có định danh, sắp xếp đúng theo metadata và báo lỗi dữ liệu thiếu/không hợp lệ.
3. Phần mềm phân tích được ảnh UAV của nhiệm vụ, nhận dạng cây trồng và cỏ dại, đồng thời lưu kết quả truy vết đến ảnh nguồn.
4. Phần mềm tạo được heatmap toàn khu vực từ dữ liệu có GPS hoặc lưới vị trí; không tạo kết quả địa lý sai khi dữ liệu không đủ vị trí.
5. Phần mềm xuất được báo cáo/CSV có kết quả tổng hợp và chi tiết cho từng drone.
6. Demo tối thiểu sử dụng một nhiệm vụ thực hoặc mô phỏng gồm ba bộ dữ liệu, ở độ cao bay nằm trong khoảng 10-20 m.

## 9. Thứ tự triển khai ưu tiên

1. Định nghĩa định dạng `mission.json` và `flight_log.csv`; xây dựng màn hình nhập nhiệm vụ ba drone.
2. Đọc EXIF/nhật ký, chuẩn hóa metadata và kiểm tra tính hợp lệ dữ liệu.
3. Gắn `mission_id`, `drone_id`, vị trí vào toàn bộ kết quả AI và CSV.
4. Xây dựng ghép kết quả theo GPS/lưới và heatmap toàn khu vực.
5. Bổ sung dashboard/báo cáo nhiệm vụ; sau đó mới cân nhắc tích hợp telemetry hoặc realtime.
