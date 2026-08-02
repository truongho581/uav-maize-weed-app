# Phase 9.5 - GreenEye, đội bay 1-3 drone và lập kế hoạch nhiệm vụ

## 0. Vị trí trong roadmap

Roadmap hiện dành Phase 10 cho đóng gói/CI đa nền tảng và Phase 11 cho hardening/nghiệm
thu. Phase 9.5 được chèn sau Phase 9 và trước đóng gói để bổ sung các yêu cầu trong
`yeucau.txt` mà không đổi số hoặc ý nghĩa của hai phase đã chốt.

## 1. Nguồn yêu cầu

Phase này tổng hợp năm yêu cầu trong `yeucau.txt`:

1. Một nhiệm vụ nhận dữ liệu từ 1, 2 hoặc 3 drone; 3 là giới hạn tối đa.
2. Người dùng tạo vùng khảo sát bằng polygon hoặc tọa độ, cấu hình chuyến bay và xuất
   hành trình dừng-chụp cho từng drone để phần mềm điều khiển đọc.
3. Các chức năng và model AI có trợ giúp ngữ cảnh bằng nút thông tin.
4. Sidebar có thể mở rộng để hiện cả biểu tượng và tên màn hình.
5. Tên sản phẩm hiển thị là **GreenEye**.

## 2. Kết luận phân tích

### 2.1. Số drone hiện đang bị khóa cứng

`SurveyMission` hiện yêu cầu đúng 3 assignment. CLI, REST API, tài liệu và nhiều test cũng
kiểm tra đúng 3 giá trị. Các service import/workspace phần lớn đã lặp theo assignment nên có
thể hỗ trợ số lượng biến thiên sau khi gỡ invariant này.

Quy tắc mới là:

- `MIN_DRONE_COUNT = 1` và `MAX_DRONE_COUNT = 3`.
- Drone ID và `lane_index` vẫn duy nhất.
- `lane_index` phải liên tục từ 0 đến `drone_count - 1`.
- Mission cũ có 3 drone vẫn đọc được, không yêu cầu chuyển đổi dữ liệu thủ công.
- Mission có 1 hoặc 2 drone không bị đánh dấu thiếu dữ liệu chỉ vì không đủ 3 drone.

### 2.2. Project mới có khả năng đọc kế hoạch, chưa tạo kế hoạch

Phase 9 đã có `QGroundControlPlanReader` và adapter MAVSDK chỉ đọc. Chưa có:

- Domain model cho vùng khảo sát và đường bay được tính toán.
- Thuật toán sinh đường quét song song và điểm dừng chụp.
- Phân chia đường bay cho 1-3 drone.
- Writer xuất file nhiệm vụ cho phần mềm điều khiển.
- UI vẽ/chỉnh polygon và xem trước hành trình từng drone.

Do đó câu “xử lý điều khiển kết hợp 3 drone” trong phạm vi Phase 9.5 được diễn giải là:

> GreenEye lập kế hoạch phối hợp tối đa 3 drone và xuất nhiệm vụ máy đọc được. Phase này
> không arm, cất cánh, upload hay khởi chạy nhiệm vụ trên drone thật.

Điều khiển realtime chỉ được tuyên bố sau phase riêng về SITL, giao thức điều khiển, giám sát
liên kết, hủy nhiệm vụ, geofence, failsafe và thử nghiệm thực địa.

### 2.3. Thông số bắt buộc để lập đường bay

- Polygon vùng khảo sát theo WGS84.
- Số drone: 1, 2 hoặc 3.
- Độ cao bay AGL và góc gimbal mặc định `-90°`.
- Camera profile đã lưu: FOV hoặc sensor/focal length đủ để tính footprint/GSD.
- Overlap dọc và overlap ngang.
- Chế độ `stop_and_capture`.
- Tốc độ hành trình, thời gian dừng chụp và hướng quét mong muốn hoặc chế độ tự động.
- Điểm home của từng drone; nếu chưa có chỉ được xem trước, chưa được xuất bản nhiệm vụ.

Độ cao Phase 9.5 là độ cao tương đối cố định so với điểm cất cánh. Terrain following cần DEM
và thuộc phase sau; UI phải ghi rõ giới hạn này.

## 3. Phạm vi kiến trúc

### 3.1. Domain mới

```text
SurveyArea
  polygon_wgs84
  projected_crs

MissionPlanningProfile
  drone_count
  altitude_agl_m
  gimbal_pitch_deg
  forward_overlap
  side_overlap
  flight_speed_mps
  capture_pause_seconds
  sweep_heading_deg | auto

CaptureWaypoint
  sequence
  latitude
  longitude
  altitude_agl_m
  action = stop_and_capture
  hold_seconds

DroneRoute
  drone_id
  home
  lane_indices
  waypoints
  estimated_distance_m
  estimated_duration_seconds

PlannedMission
  mission_id
  survey_area
  profile
  routes[1..3]
  warnings
  generator_version
```

Domain không import Qt, Leaflet, MAVSDK hoặc QGroundControl.

### 3.2. Application ports

- `MissionPlanner.plan(request) -> PlannedMission`.
- `MissionPlanRepository.save/get/list` để kế hoạch tồn tại sau khi mở lại app.
- `MissionPlanExporter.export(plan, format, output_dir)`.
- `MissionPlanValidator.validate(plan)` chạy trước khi cho phép xuất.

SDK/CLI/REST chỉ gọi các application service trên. Không đặt thuật toán đường bay trong UI.

### 3.3. Định dạng xuất

Xuất một bundle thay vì một file mơ hồ:

```text
GreenEye mission/
  <mission-id>/
  mission.json
  qgroundcontrol/
    drone-01.plan
    drone-02.plan
    drone-03.plan
  checksums.sha256
```

`mission.json` là contract trung gian ổn định của GreenEye, chứa polygon, profile, camera
profile ID/checksum, home, waypoint WGS84, hành động dừng-chụp và thống kê từng route.
Các file QGC `.plan` là đầu ra để nạp cho từng drone, với số file đúng bằng số drone đã chọn.

Không ghi đường dẫn tuyệt đối của máy nguồn vào bundle. Schema có version và tất cả file dùng
UTF-8. Writer phải được kiểm tra round-trip bằng reader hiện có.

## 4. Thuật toán lập kế hoạch

1. Validate polygon WGS84: tối thiểu 3 đỉnh, không tự cắt, diện tích lớn hơn 0.
2. Chọn CRS phẳng cục bộ phù hợp từ tâm polygon và chuyển geometry sang mét.
3. Tính footprint camera tại độ cao AGL.
4. Tính khoảng cách giữa các làn:
   `lane_spacing = footprint_width * (1 - side_overlap)`.
5. Tính khoảng cách giữa hai điểm chụp:
   `capture_spacing = footprint_height * (1 - forward_overlap)`.
6. Chọn hướng quét tự động để giảm tổng chiều dài quay đầu, hoặc dùng heading người dùng.
7. Sinh các đường song song, clip theo polygon và sắp theo kiểu boustrophedon.
8. Đặt các điểm dừng-chụp dọc mỗi đoạn; không tạo điểm ngoài polygon trừ điểm home/transit.
9. Chia các làn liền kề cho 1-3 drone để cân bằng quãng đường và số điểm chụp.
10. Nối home, transit, route và return-home; tính quãng đường/thời gian ước lượng.
11. Chạy validator và chỉ bật xuất file khi không có lỗi chặn.

Planner phải deterministic: cùng input và version cho cùng output. Không dùng thứ tự ngẫu
nhiên. Sai số geometry, điểm sát biên và polygon lõm phải có test riêng.

Phase này chưa giải quyết tránh va chạm động. Khi các drone bay đồng thời, route phải được
chia thành dải liền kề và cảnh báo nếu khoảng cách giữa hai tuyến nhỏ hơn ngưỡng cấu hình.

## 5. Thiết kế UI

### 5.1. Màn hình “Lập nhiệm vụ”

- Thêm một mục sidebar riêng trước màn Dữ liệu.
- Trung tâm là bản đồ vệ tinh/địa hình, không đặt trong card trang trí.
- Toolbar trên bản đồ: vẽ polygon, sửa đỉnh, xóa, nhập tọa độ, vừa vùng và hoàn tác.
- Panel trái: vùng khảo sát, camera profile, độ cao, overlap, số drone và hướng quét.
- Panel phải: danh sách route theo màu, khoảng cách, thời gian, số làn và số ảnh dự kiến.
- Bảng dưới: waypoint của route đang chọn, gồm thứ tự, tọa độ, độ cao và hành động.
- Nút chính: `Tính đường bay`; chỉ sau khi validate mới bật `Xuất nhiệm vụ`.

Màu route không phải tín hiệu duy nhất; luôn có nhãn `Drone 1`, `Drone 2`, `Drone 3` và kiểu
đường khác nhau. Polygon, route và waypoint có checkbox bật/tắt.

### 5.2. Trợ giúp ngữ cảnh

Tạo component dùng chung `InfoButton`:

- Biểu tượng `circle-help` hoặc `info`, tooltip ngắn khi hover.
- Click mở popover/dialog nhỏ có tiêu đề, mô tả, đơn vị, ảnh hưởng và giá trị khuyến nghị.
- Có accessible name, focus bằng bàn phím và nút đóng rõ ràng.
- Không rải đoạn hướng dẫn dài trực tiếp trên màn hình chính.

Ưu tiên gắn trợ giúp cho: semantic/instance, threshold, tile, overlap ảnh AI, overlap bay,
GSD, AGL, CRS, NodeODM, heatmap và độ chính xác định vị.

### 5.3. Sidebar mở rộng

- Thu gọn: 56 px, chỉ icon và tooltip như hiện tại.
- Mở rộng: 190-210 px, icon + tên màn hình.
- Nút toggle dùng icon `panel-left-open/close`.
- Trạng thái lưu bằng `QSettings` và được khôi phục lần mở sau.
- Khi cửa sổ hẹp, sidebar tự thu gọn nhưng không ghi đè lựa chọn dài hạn của người dùng.
- Nội dung trung tâm không bị nhảy sai splitter hoặc che chữ khi toggle.

### 5.4. Đổi tên GreenEye

- Window title, nhãn sản phẩm, About, báo cáo và tài liệu người dùng đổi thành `GreenEye`.
- Tên mô tả: `GreenEye - Phân tích và lập kế hoạch khảo sát cây trồng`.
- Package Python `uav_crop_analysis`, database schema và model ID không đổi.
- Chưa đổi ngay thư mục dữ liệu người dùng cũ để tránh mất mission, camera profile và job.
- Nếu đổi bundle/executable và app-data path, phải có migration tự động, idempotent và backup.

## 6. Chia công việc

### Phase 9.5.1 - Đội bay 1-3 drone

- Sửa invariant domain, command, manifest, SQLite mapping, SDK, CLI và REST.
- Cập nhật workspace/report để số tab và chỉ số drone là động.
- Giữ tương thích mission ba drone hiện có.

Kiểm tra: tạo/import/mở lại mission 1, 2, 3 drone; từ chối 0 và 4 drone; migration và API
backward compatibility.

### Phase 9.5.2 - Lõi mission planner

- Thêm domain/ports, phép chiếu, footprint, grid, capture points và cân bằng route.
- Chưa làm UI; chạy bằng fixture và unit test.

Kiểm tra: polygon chữ nhật/lõm/xoay, 1-3 drone, camera profile khác nhau, overlap biên,
deterministic output và coverage không có vùng mù theo mô hình footprint.

### Phase 9.5.3 - Export và contract tích hợp

- GreenEye mission schema, JSON writer, QGC writer và checksum bundle.
- Thêm SDK, CLI và REST endpoint lập/xuất kế hoạch.
- Capabilities thêm `mission_planning=true`, vẫn giữ `drone_commands_enabled=false`.

Kiểm tra: schema validation, round-trip writer-reader, đường dẫn portable và fixture golden.

### Phase 9.5.4 - UI lập nhiệm vụ

- Bản đồ vẽ/import polygon, form tham số, route layers, waypoint table và export dialog.
- Lưu draft tự động và khôi phục khi mở app.

Kiểm tra: screenshot 1180x760, 1440x900, 1920x1080; polygon rỗng/lỗi; bàn phím; text Việt;
route 1-3 drone; đóng/mở lại draft.

### Phase 9.5.5 - Trợ giúp, sidebar và GreenEye

- `InfoButton`, nội dung trợ giúp có version.
- Sidebar mở rộng/thu gọn và persistence.
- Đổi brand hiển thị, icon và tài liệu; migration tên ứng dụng nếu cần.

Kiểm tra: QSettings, responsive layout, tooltip/focus, không mất dữ liệu app cũ và frozen smoke.

### Phase 9.5.6 - Review tích hợp

- Chạy full test, Ruff, MyPy, golden planner và build ba nền tảng.
- Import các file QGC sinh ra vào QGroundControl để review trực quan.
- Chạy tối thiểu ba vehicle PX4/ArduPilot SITL ở chế độ không upload từ GreenEye.
- Review an toàn và ghi rõ giới hạn trước khi demo/nghiệm thu.

## 7. Tiêu chí nghiệm thu Phase 9.5

- GreenEye tạo và quản lý mission có 1, 2 hoặc 3 drone.
- Người dùng vẽ hoặc nhập polygon và xem được đường bay/điểm dừng-chụp từng drone.
- Khoảng cách làn và điểm chụp truy ngược được về camera, độ cao và overlap.
- Mỗi drone nhận route liền kề, deterministic và có thống kê quãng đường/thời gian/ảnh.
- Bundle nhiệm vụ có schema version, checksum và đọc lại được.
- QGC mở được từng `.plan` mà không báo lỗi cấu trúc.
- Không có API/UI arm, takeoff, upload hoặc start mission trong phase này.
- Sidebar mở rộng ổn định; trợ giúp ngữ cảnh không chiếm diện tích chính.
- Tên GreenEye hiển thị nhất quán và dữ liệu ứng dụng cũ không bị mất.
- Các test cũ về inference, orthomosaic, heatmap, report và SDK vẫn đạt.

## 8. Rủi ro và phần không tuyên bố

- Coverage tính theo mô hình footprint camera; không thay thế hiệu chuẩn thực địa.
- Không có DEM thì không bảo đảm AGL cố định trên địa hình dốc.
- Không có no-fly database, obstacle avoidance hoặc tránh va chạm động.
- Thời lượng pin chỉ là ước lượng nếu chưa nhập tốc độ, thời gian dừng và reserve.
- File nhiệm vụ phải được người vận hành kiểm tra trong QGC/phần mềm điều khiển trước khi bay.
- Việc drone có hỗ trợ đầy đủ lệnh dừng-chụp phụ thuộc autopilot/camera adapter cụ thể.

## 9. Thứ tự triển khai đề xuất

Bắt đầu bằng Phase 9.5.1. Không làm giao diện planner trước khi domain chấp nhận 1-3 drone,
vì toàn bộ route, report, API và mission export phụ thuộc contract này. Sau mỗi phase con phải
chạy test, chụp UI nếu có, review diff và chỉ chuyển bước khi tiêu chí tương ứng đạt.
