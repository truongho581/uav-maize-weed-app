# Review Phase 4 - Pipeline job và worker process

Ngày review: 2026-07-27.

## Kết luận gate

**Đạt điều kiện chuyển sang Phase 5.** Semantic analysis chạy ngoài UI process, job
được persist qua SQLite, hỗ trợ queue/progress/cancel/retry/recovery và chỉ công bố
artifact sau atomic completion. Instance pipeline vẫn chờ checkpoint như Phase 3.

## Đã hoàn thành

- `AnalysisJob` state machine và cấu hình input/model/tile/output bất biến.
- SQLite migration v2 cho job và event history; migration từ database v1.
- Semantic tile inference, overlap probability blending và weed metrics.
- Atomic artifact directory, per-file checksum, manifest và completion marker.
- Spawn worker process cùng structured progress/result/error message.
- Parent-process service sở hữu persistence; worker không truy cập SQLite/UI.
- Cancel event, retry attempt, interrupted-worker recovery và stale staging cleanup.
- Queue dispatcher có `max_workers=1` mặc định để kiểm soát RAM.
- Progress coalescing để giảm event transaction khi mission có nhiều tile.

## Verification

| Kiểm tra | Kết quả |
| --- | --- |
| Phase 4 focused tests | 14/14 passed |
| State transition/progress | Invalid transition và progress lùi bị từ chối |
| SQLite reopen | Job/config/error/result/event giữ nguyên |
| Migration v1 -> v2 | Passed |
| Single-process vs worker | Probability raster khớp trong tolerance `1e-6` |
| Cancel/retry | Không có attempt giả; retry xuất attempt mới |
| File/model/OOM mô phỏng | Structured error code và retryability đúng |
| App restart | Running job thành retryable failure; staging được dọn |
| Stress 18 ảnh | Completed; parent tiếp tục poll; progress được coalesce |
| Worker capacity | Dispatcher chỉ chạy đúng số slot |
| Full test suite | 71/71 passed; package coverage 83% |
| Ruff / mypy / lockfile / diff check | Passed |
| Build và cài wheel ngoài source | SQLite v2 và job/event round-trip passed |

## Real checkpoint smoke

SegFormer-B0 D1, ảnh RGB `640 x 640`, CPU, chạy qua process worker thật:

- status: `completed`;
- elapsed end-to-end: `3977.6 ms` gồm spawn, import, checksum, load và inference;
- event persisted: `5`;
- artifact có `manifest.json`, `COMPLETED.json` và manifest SHA-256 hợp lệ.

Số này là smoke benchmark trên máy phát triển, không phải SLA phát hành.

## Phần để mở

1. Instance tile merge/NMS sẽ được thêm khi có checkpoint YOLOv8/Mask R-CNN thật.
2. Job hiện xử lý danh sách ảnh semantic; orthomosaic/georeference thuộc Phase 7.
3. Scheduler hiện giới hạn theo số worker, chưa tự tính RAM/GPU capacity.
4. Worker log rotation, process priority và hard resource limits cần kiểm tra theo OS.
5. Phase 5 sẽ nối job state/event vào PySide6 viewmodel, không đổi process contract.
