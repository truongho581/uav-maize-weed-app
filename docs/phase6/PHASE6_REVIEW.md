# Review Phase 6 - Data và Analysis workspace

Ngày review: 2026-07-27.

## Kết luận gate

**Hoàn thành Phase 6 theo phạm vi checkpoint hiện có.** Luồng weed semantic chạy từ
mission data tới persisted job, process worker và result viewer. Maize instance được
tách đúng contract nhưng bị khóa có chủ đích vì checkpoint instance sẽ bổ sung sau.
Orthomosaic và heatmap địa lý tiếp tục ở Phase 7.

## Đã hoàn thành

- Data workspace chia đúng ba drone/làn, bảng ảnh/metadata, lỗi và bộ lọc.
- Import `mission.json` chạy nền; EXIF, telemetry sync và checksum không chặn UI thread.
- Analysis workspace tách `weed semantic` và `maize instance` bằng task contract.
- Model/checkpoint/device/tile/overlap/threshold controls và persisted job queue.
- Poll progress, cancel, retry, restart recovery và shutdown worker an toàn.
- Viewer original, weed mask, probability, overlay, opacity, zoom, fit và inspector.
- Composition root độc lập path Windows/Linux/macOS; model registry có override env.
- PyInstaller Phase 6 chứa semantic runtime; checkpoint/model pack vẫn tách khỏi app.

## Verification

| Kiểm tra | Kết quả |
| --- | --- |
| Phase 6 service/UI focused tests | 9 passed |
| Full regression suite | 90 passed; package coverage 84% |
| Semantic/instance boundary | Weed chỉ semantic; maize chỉ instance |
| Background import controller | Completed signal và thread cleanup passed |
| Result layer render | 4/4 layer nonblank; mask color/shape checked |
| Real SegFormer worker smoke | Completed, 3978.8 ms, 6 persisted events |
| Real artifact | Probability NPY, weed mask PNG, manifest/completion marker |
| Screenshot matrix | 6/6 passed at 1366x768, 1440x900, 1920x1080 |
| Frozen macOS smoke | App alive, SQLite created; bundle 683 MB |

Thời gian smoke là số đo trên máy phát triển, không phải SLA.

## Phần để mở

1. Bổ sung checkpoint và worker YOLOv8/Mask R-CNN cho maize instance.
2. UI mapping folder/CSV cụ thể chờ cấu trúc dữ liệu drone thực; manifest contract đã
   ổn định để không khóa vào layout đoán trước.
3. Disk quota/preflight và cancellation giữa chừng của import dài thuộc hardening.
4. Phase 7 thêm ODM/orthomosaic, georeference và heatmap toàn khu vực ba drone.
5. Phase 10 build và smoke native Windows/Linux; PyInstaller không cross-compile.
