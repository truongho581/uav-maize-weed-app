# Checklist tích hợp Phase 9.5

Ngày rà soát cục bộ: 30/07/2026.

## 1. Trạng thái kiểm chứng

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Mission 1, 2 và 3 drone | Đạt | `tools/phase9_5_integration_audit.py` |
| Planner deterministic | Đạt | Lập lại cùng request và so sánh toàn bộ `PlannedMission` |
| Độ phủ footprint | Đạt với fixture | Tỷ lệ `1.0` trên thửa chữ nhật 80 x 50 m |
| Route liền kề | Đạt | Làn được phân liên tục, không đổi thứ tự ngẫu nhiên |
| Bundle và checksum | Đạt | Bundle có 3/5/7 file được kiểm tra SHA-256 cho 1/2/3 drone |
| QGC JSON round-trip | Đạt | `QGroundControlPlanReader` đọc đủ waypoint, chỉ có lệnh 16 và 206 |
| Import trực quan trong QGC 5.0 | Chưa chốt | QGC không nhận `.plan` bằng đối số dòng lệnh; cần mở từ màn Plan |
| PX4/ArduPilot SITL ba vehicle | Chưa chạy | Máy rà soát chưa cài PX4 hoặc ArduPilot SITL |
| Ruff | Đạt | `ruff check .` |
| MyPy | Đạt | `mypy` theo cấu hình `pyproject.toml` |
| Test hồi quy | Đạt | `205 passed, 1 deselected` |
| Build macOS và frozen smoke | Đạt | PyInstaller hoàn tất; executable sống ổn định trong smoke 10 giây |
| Build Windows/Linux | Chưa chạy | Workflow `.github/workflows/phase9_5_cross_platform.yml` đã sẵn sàng |

`Đạt với fixture` chỉ chứng minh contract hình học trên dữ liệu chuẩn. Nó không thay thế
hiệu chuẩn camera, thử ngoài thực địa hoặc đánh giá tránh va chạm.

SHA-256 executable macOS đã kiểm tra:
`1a1fd23ca9dd6be629d0a650358820a054ce572575f858dedb94d8684bfa7b03`.

## 2. Golden audit

Chạy lại audit độc lập bằng lệnh:

```bash
python tools/phase9_5_integration_audit.py --output project_data/phase9_5_review
pytest -q tests/test_phase9_5_integration_audit.py
```

Fixture cố định nằm tại `tests/fixtures/phase9_5/planner_audit_golden.json`. Audit kiểm tra:

- tổng diện tích, tỷ lệ phủ, khoảng cách làn và khoảng cách chụp;
- số làn, điểm chụp, quãng đường và thời gian của từng drone;
- tính ổn định của kết quả khi chạy lại cùng dữ liệu;
- checksum của mọi file trong bundle;
- số waypoint và tập lệnh của từng file QGroundControl;
- SDK không công khai `arm`, `takeoff`, `upload_mission` hoặc `start_mission`.

## 3. Review QGroundControl

QGroundControl 5.0 trên macOS đã được khởi động offline. Phiên bản này không khai báo tham
số dòng lệnh để tự nạp `.plan`, nên đường dẫn truyền khi mở ứng dụng bị bỏ qua. Để chốt mục
review trực quan, người kiểm tra thực hiện cho cả ba file trong bundle golden:

1. Mở QGroundControl, chuyển sang `Plan`.
2. Chọn `File` > `Open` và mở lần lượt `drone-01.plan`, `drone-02.plan`, `drone-03.plan`.
3. Xác nhận không có lỗi format, điểm bay nằm trong vùng dự kiến và độ cao là 10 m AGL.
4. Kiểm tra hành động waypoint gồm bay tới điểm và đặt gimbal nadir; không upload tới drone.

Không đánh dấu mục này đạt chỉ dựa trên việc QGroundControl khởi động được.

## 4. Review SITL ba vehicle

PX4 SIH là đường kiểm tra nhẹ phù hợp cho ba vehicle. Trên môi trường đã cài PX4-Autopilot:

```bash
make px4_sitl_sih sihsim_quadx
./Tools/simulation/sitl_multiple_run.sh 3 sihsim_quadx px4_sitl_sih
```

Tiêu chí chốt:

- QGroundControl nhìn thấy ba vehicle có system ID khác nhau;
- ba route mở riêng không báo lỗi và không bị gán nhầm drone;
- GreenEye chỉ xuất file, không kết nối để arm/upload/start;
- dừng một SITL không làm GreenEye mất plan hoặc bundle đã xuất.

## 5. Giới hạn an toàn

- GreenEye Phase 9.5 là công cụ lập và xuất kế hoạch, không phải bộ điều khiển bay realtime.
- Không có tránh va chạm động, geofence theo vùng cấm, DEM terrain-following hoặc đánh giá pin
  theo phần cứng thật.
- Home, camera, overlap, AGL và route phải được người vận hành kiểm tra trong phần mềm điều
  khiển trước mỗi chuyến bay.
- Thử SITL không đủ để cho phép bay thật; cần hiệu chuẩn và quy trình thử nghiệm thực địa riêng.
