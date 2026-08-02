# Review Phase 9.5.1 - Mission 1-3 drone

## Kết quả

Phase 9.5.1 đã chuyển contract mission từ đúng ba drone sang từ một đến tối đa ba
drone. Kịch bản ba drone vẫn là cấu hình đầy đủ để nghiệm thu đề tài; mission một hoặc
hai drone phục vụ thu thập nhỏ, kiểm tra model và vận hành khi chưa cần đủ tổ hợp.

## Thay đổi đã thực hiện

- Domain dùng `MIN_DRONE_COUNT = 1` và `MAX_DRONE_COUNT = 3`.
- Drone ID phải duy nhất; lane phải liên tục từ `0` đến `n-1`.
- Application command và SDK DTO nhận tuple có độ dài động.
- REST `POST /api/v1/missions` và CLI `mission create` nhận 1-3 drone.
- Manifest schema 1 nhận 1-3 hàng drone và kiểm tra lane liên tục.
- SQLite lưu/đọc assignment động; không cần migration database.
- Data workspace tạo số tab đúng bằng số drone của mission.
- Mission report và HTML hiển thị số drone thực tế, không khóa đúng ba drone.
- Tài liệu nhập liệu, geospatial, report, SDK/API và hướng dẫn sử dụng đã đồng bộ.

## Tương thích

- Mission và manifest ba drone hiện có vẫn hợp lệ, không cần chuyển đổi dữ liệu.
- Database schema vẫn ở version 4 vì bảng `drone_assignments` vốn không khóa số hàng.
- REST tiếp tục dùng `/api/v1`; thay đổi chỉ nới miền giá trị đầu vào nên tương thích
  với client cũ.
- Stream mô phỏng tích hợp vẫn tạo ba drone vì đây là fixture demo tổ hợp đầy đủ.

## Ma trận kiểm thử

| Luồng | 1 drone | 2 drone | 3 drone | 0 drone | 4 drone |
| --- | --- | --- | --- | --- | --- |
| Domain | Nhận | Nhận | Nhận | Từ chối | Từ chối |
| Manifest | Nhận | Nhận | Nhận | Từ chối | Từ chối |
| SQLite round-trip | Đạt | Đạt | Đạt | Không áp dụng | Không áp dụng |
| SDK | Đạt | Đạt | Đạt | Domain từ chối | Domain từ chối |
| REST | Hỗ trợ | Hỗ trợ | Hỗ trợ | HTTP 400 | HTTP 400 |
| CLI | Đạt | Đạt | Đạt | Parser yêu cầu ít nhất một | Exit code 2 |
| UI Data | Đúng số tab | Đúng số tab | Hồi quy đạt | Không áp dụng | Không áp dụng |
| Report | Đạt | Contract động | Hồi quy đạt | Không áp dụng | Không áp dụng |

## Quality gate

- `ruff check .`: đạt.
- `pytest -q`: 165 test đạt.
- MyPy giới hạn trên 10 module thay đổi với `--follow-imports=skip`: đạt.
- MyPy toàn repository còn 15 lỗi có sẵn tại `ui/components.py`,
  `application/model_test.py`, `ui/views/spatial_workspace.py`, tool tạo mission mô
  phỏng và test worker. Không có lỗi nào thuộc contract 1-3 drone; cần xử lý trong
  phase hardening riêng.
- PyInstaller build và re-sign 124 Qt framework: đạt.
- Smoke test bundle chính vào tới Qt event loop và Qt WebEngine: đạt.
- SHA-256 executable: `d8857f700c1419f5c4c2fadd296a123a7b0a8d596939f2a26b4cef1d84163835`.

## Giới hạn còn lại

- UI chưa có trình tạo mission thủ công; hiện mission 1-3 drone được tạo qua manifest,
  SDK, CLI hoặc REST.
- Phase này chưa chia polygon, tính đường bay, điểm dừng chụp hoặc xuất kế hoạch bay.
  Các chức năng đó thuộc Phase 9.5.2 trở đi.
- Không bổ sung lệnh arm, takeoff, upload mission hay start mission; ranh giới tích hợp
  drone vẫn read-only.

## Kết luận

Phase 9.5.1 đạt yêu cầu hỗ trợ dữ liệu từ một, hai hoặc tối đa ba drone và giữ tương
thích với mission ba drone hiện có. Có thể chuyển sang Phase 9.5.2 để xây dựng domain
polygon, thông số camera/GSD và bộ tính footprint trước khi sinh đường bay.
