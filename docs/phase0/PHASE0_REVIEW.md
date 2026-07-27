# Review Phase 0 - Baseline và safety net

Ngày review: 2026-07-27.

## Kết luận gate

**Có thể bắt đầu Phase 1 về kiến trúc, nhưng AI golden gate đang chờ checkpoint instance v7.2.** Checkpoint legacy `models/best.pt` đã bị loại khỏi project theo quyết định ngày 2026-07-27; không dùng kết quả hoặc benchmark của model này làm chuẩn nữa.

## Đã hoàn thành

- Chốt Python 3.11, `pyproject.toml`, `uv.lock` và `requirements-dev.lock`.
- Kiểm kê dataset MaizeMask v7.2, class map và split train/validation/test.
- Xác minh SHA-256 của 9 checkpoint semantic LOSO: Attention U-Net, DeepLabV3+ và SegFormer-B0.
- Ghi rõ hợp đồng: ngô dùng instance segmentation; weed dùng semantic segmentation.
- Thêm unit tests cho class contract, tile stitching, chỉ số nông học và heatmap.
- Audit sơ bộ license của UI, runtime AI, orthomosaic và công cụ đóng gói.
- Sửa lỗi runtime `cv2.COLORMAP_RdYlGn` không tồn tại.
- Bỏ model mặc định khỏi UI; ứng dụng khởi động ở trạng thái chưa chọn model.

## Kết quả kiểm tra

| Kiểm tra | Kết quả |
| --- | --- |
| `python tools/verify_phase0_assets.py` | 9 artifact semantic hợp lệ; 2 model instance đang chờ path |
| `python -m pytest -ra` | Passed; chưa có golden AI chính thức |
| `python -m ruff check .` | Passed |
| `python -m mypy` | Passed |
| UI import smoke test | Passed |
| `uv lock --check` | Passed |
| `git diff --check` | Passed |

## Rủi ro và quyết định còn mở

1. Chưa có checkpoint YOLOv8 và Mask R-CNN instance v7.2 trong workspace hiện tại.
2. Chín checkpoint semantic hiện có là checkpoint LOSO phục vụ đánh giá, chưa phải model deployment cuối.
3. Chưa thể khóa regression cho mask, số cây, stage count, latency và RAM cho đến khi chọn checkpoint triển khai.
4. PyQt5 và Ultralytics có điều kiện giấy phép cần xử lý trước khi phát hành binary. Roadmap vẫn giữ hướng PySide6 + ONNX Runtime.

## Đầu vào cần chốt cho Phase 3

- Đường dẫn tuyệt đối tới checkpoint YOLOv8 segmentation v7.2.
- Đường dẫn tuyệt đối tới checkpoint Mask R-CNN v7.2.
- Checkpoint semantic deployment, hoặc xác nhận tạo model cuối sau khi chọn kiến trúc thắng.
