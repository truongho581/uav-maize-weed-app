# Phase 9.5.4 - Contract giao diện lập nhiệm vụ

## Mục tiêu

Màn **Lập nhiệm vụ** cho phép người vận hành chuẩn bị và kiểm tra trực quan kế hoạch quét
một vùng bằng một đến ba drone. Màn hình chỉ tạo, xem trước và xuất tệp; không điều khiển
drone, arm, cất cánh hoặc tự tải nhiệm vụ lên autopilot.

## Bố cục

- Cột trái: camera đã lưu, AGL, overlap, số drone và home WGS84.
- Trung tâm: bản đồ vệ tinh, polygon khảo sát, route theo màu và điểm chụp.
- Phía dưới bản đồ: bảng waypoint của route đang chọn.
- Cột phải: diện tích, coverage, số ảnh, bật/tắt route, chỉ số route và cảnh báo.

Bố cục giữ nguyên ba vùng ở 1180x760, 1440x900 và 1920x1080. Sidebar chỉ dùng biểu
tượng để dành chiều rộng cho bản đồ.

## Tạo vùng khảo sát

Toolbar bản đồ hỗ trợ:

- Vẽ polygon bằng các điểm click và kết thúc bằng cách tắt chế độ vẽ.
- Kéo đỉnh để sửa polygon.
- Hoàn tác đỉnh cuối, xóa polygon và vừa khung.
- Import tọa độ từ từng dòng `latitude, longitude` hoặc JSON array.

Polygon được lưu theo WGS84. UI không tự suy ra ranh giới từ ảnh, không sửa
self-intersection và không thay đổi tọa độ để làm đẹp hình; lỗi hình học do planner trả về.

## Cấu hình và tính toán

- Camera lấy từ catalog dài hạn, không yêu cầu nhập lại kích thước ảnh trong mission.
- AGL, overlap dọc/ngang và số drone là cấu hình chính.
- Dialog nâng cao chứa tốc độ, thời gian dừng chụp, heading và khoảng cách route tối thiểu.
- Gimbal giữ mặc định nadir `-90` theo contract lõi.
- Mỗi drone có thể bật home và nhập latitude/longitude riêng.

Nút **Tính đường bay** gửi `PlanningDraft` qua tác vụ nền. UI không chứa thuật toán hình
học; mọi kết quả đến từ `MissionPlanningService` dùng chung với SDK, CLI và REST.

## Hiển thị kết quả

- Drone 1, 2 và 3 lần lượt dùng xanh lá, xanh lam và cam; route có kiểu nét khác nhau.
- Bảng route cho phép bật/tắt từng lớp và chọn route cần xem waypoint.
- Bảng waypoint dùng model ảo để không tạo hàng nghìn widget khi plan lớn.
- Bản đồ giới hạn số điểm render để giữ phản hồi UI; bảng và tệp xuất vẫn dùng toàn bộ
  waypoint của plan.
- Cảnh báo kỹ thuật từ planner được chuyển thành thông báo tiếng Việt, không đổi mã warning
  trong dữ liệu lưu.

## Draft, plan và trạng thái cũ

Draft được tự lưu bằng `QSettings`, tách theo hash của mission ID. Draft lưu cả polygon,
camera, cấu hình bay, home và route đang bật.

Plan đã tính được lưu bằng `MissionPlanningService`. Khi mở lại mission:

- Draft khớp plan: cho phép xuất nếu `export_ready=true`.
- Draft khác plan: vẫn hiển thị plan cũ để tham khảo nhưng gắn trạng thái **Cần tính lại** và
  khóa xuất.
- Mọi thay đổi đầu vào sau khi tính đều làm plan thành cũ cho đến lần tính kế tiếp.

## Điều kiện xuất

Nút **Xuất nhiệm vụ** chỉ bật khi:

- Có plan đã tính và plan không cũ.
- Plan có home cho mọi drone và `export_ready=true`.
- Không có tác vụ tính hoặc xuất đang chạy.

Export tạo bundle GreenEye/QGroundControl theo contract Phase 9.5.3. Người vận hành vẫn
phải kiểm tra tệp bằng autopilot/camera và quy trình bay thật trước khi sử dụng.

## Ranh giới

- Lớp nền vệ tinh chỉ phục vụ định hướng; không phải nguồn địa chính hoặc geofence.
- Chưa có DEM, terrain following, tránh vật cản, đánh giá pin/gió hoặc tránh va chạm động.
- Home và polygon do người dùng nhập; UI không xác nhận khả năng cất/hạ cánh tại thực địa.
- Phase này chưa xác nhận bằng QGroundControl thật hoặc SITL đa vehicle.
