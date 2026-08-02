# Phase 9.5.2 - Contract lõi lập kế hoạch nhiệm vụ

## Phạm vi

Package `uav_crop_analysis.planning` tạo bản xem trước đường quét dừng-chụp cho một đến
ba drone. Package độc lập Qt, không đọc/ghi SQLite và không gửi lệnh tới autopilot.

Phase này chưa xuất QGroundControl, chưa lưu plan và chưa có UI. Các phần đó thuộc Phase
9.5.3 và 9.5.4.

## Đầu vào

`MissionPlanningRequest` gồm:

- Mission ID.
- Polygon WGS84 có ít nhất ba đỉnh duy nhất.
- `MissionPlanningProfile`: 1-3 drone, AGL 10-20 m, gimbal nadir `-90`, overlap,
  tốc độ, thời gian dừng và heading tùy chọn.
- `CameraProfile` có HFOV/VFOV; có thể thiếu một FOV nếu có tỷ lệ ảnh để suy ra.
- Drone ID duy nhất và home tương ứng. Home có thể thiếu ở chế độ preview.
- Kích thước pixel tùy chọn lấy từ metadata ảnh để tính GSD; không phải thông số người
  dùng buộc nhập lại vào hồ sơ camera.

Tiêu cự đơn lẻ không đủ để tính footprint khi thiếu FOV hoặc kích thước cảm biến. Planner
từ chối trường hợp này thay vì ngầm dùng một camera giả định.

## Phép chiếu

- Polygon được kiểm tra self-intersection bằng Shapely.
- Nếu không truyền CRS phẳng, planner chọn UTM từ tâm polygon; vùng cực dùng UPS.
- CRS do caller truyền phải là projected CRS có đơn vị mét.
- Diện tích tối thiểu là `1 m2`.

Polygon trong kết quả vẫn là WGS84 và ghi thêm CRS phẳng đã dùng để mọi khoảng cách có
thể truy nguyên.

## Footprint và GSD

Với camera nadir:

```text
ground_width_m  = 2 * altitude_agl_m * tan(HFOV / 2)
ground_height_m = 2 * altitude_agl_m * tan(VFOV / 2)
lane_spacing_m  = ground_width_m  * (1 - side_overlap)
capture_spacing = ground_height_m * (1 - forward_overlap)
gsd_x_cm_px     = ground_width_m  / image_width_px  * 100
gsd_y_cm_px     = ground_height_m / image_height_px * 100
```

Footprint ngang được hiểu là phương vuông góc đường bay; footprint dọc cùng hướng bay.
Mô hình giả định camera không xoay yaw lệch khỏi hướng thân drone.

## Sinh đường quét

1. Chọn heading do người dùng nhập hoặc cạnh dài của minimum-area bounding orientation.
2. Xoay polygon để đường quét song song trục X.
3. Phân bố tâm làn sao cho khoảng cách không vượt `lane_spacing_m` và footprint phủ hai
   biên ngoài.
4. Cắt từng làn bằng polygon; polygon lõm có thể tạo nhiều đoạn làn.
5. Bố trí điểm chụp sao cho khoảng cách không vượt `capture_spacing_m` và footprint phủ
   hai đầu đoạn.
6. Đảo chiều từng hàng để tạo thứ tự boustrophedon xác định.
7. Chia chuỗi làn thành 1-3 nhóm liền kề bằng dynamic programming, tối thiểu hóa workload
   lớn nhất. Workload gồm chiều dài làn và thời gian dừng quy đổi theo tốc độ.
8. Chuyển waypoint về WGS84, tính quãng đường từ/về home khi có và ước lượng thời gian.

Cùng request và `generator_version` luôn cho cùng kết quả; thuật toán không dùng random.

## Coverage

Planner dựng hình chữ nhật footprint quanh mọi điểm chụp trong hệ tọa độ phẳng, hợp nhất
chúng và giao với polygon:

```text
coverage_ratio = covered_polygon_area / survey_polygon_area
```

Kế hoạch bị từ chối nếu coverage nhỏ hơn `0.999`. Đây là coverage hình học theo mô hình
camera, không phải bằng chứng ảnh thực tế sắc nét, GPS đúng, không rung hoặc không bị che.

Giới hạn bảo vệ tài nguyên là 10.000 đoạn làn và 100.000 điểm chụp cho một request.

## Kết quả

`PlannedMission` trả về:

- CRS, diện tích, heading thực tế và footprint/GSD.
- `coverage_ratio` và tổng số điểm chụp.
- Đúng số route theo drone đã chọn.
- Mỗi route có nhóm lane liền kề, waypoint, home, quãng đường và thời gian.
- Warning có mã ổn định.

`export_ready` chỉ đúng khi mọi route có home. Thiếu home không chặn preview nhưng sẽ
chặn export ở Phase 9.5.3.

## Warning hiện có

| Mã | Ý nghĩa |
| --- | --- |
| `fixed_agl_without_terrain` | Không có DEM/terrain following |
| `missing_home` | Route chỉ preview, chưa đủ điều kiện xuất |
| `route_separation_below_minimum` | Khoảng làn nhỏ hơn ngưỡng phân cách cấu hình |
| `route_workload_imbalance` | Thời lượng lớn nhất vượt 150% route nhỏ nhất |

## Ranh giới an toàn

- Không tránh vật cản, geofence, vùng cấm bay hoặc va chạm động.
- Không hiệu chỉnh địa hình dốc; AGL đang cố định tương đối theo home.
- Không đánh giá pin, gió, chất lượng GPS/RTK hoặc khả năng camera/autopilot thực tế.
- Waypoint chỉ mang ngữ nghĩa `stop_and_capture`; adapter thiết bị phải ánh xạ và được
  người vận hành kiểm tra trước chuyến bay.
- Không có API arm, takeoff, upload hoặc start mission.
