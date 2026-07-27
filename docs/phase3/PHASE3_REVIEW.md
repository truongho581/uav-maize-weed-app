# Review Phase 3 - Model registry và semantic inference

Ngày review: 2026-07-27.

## Kết luận gate

**Semantic sub-gate đạt. Instance sub-gate được hoãn theo quyết định chưa cung cấp
checkpoint.** Ba model semantic có thể đổi bằng model ID/artifact role mà không sửa
UI hoặc pipeline. YOLOv8 và Mask R-CNN vẫn trả `model_unavailable`, không fallback
sang checkpoint cũ hoặc dùng semantic crop mask để giả instance.

## Đã hoàn thành

- Registry schema v2 với class map, preprocessing, runtime, output adapter và checksum.
- DTO/protocol chung cho semantic và instance, cùng coordinate/dtype convention.
- PyTorch adapter cho Attention U-Net, DeepLabV3+ ResNet-50 và SegFormer-B0.
- Đóng gói kiến trúc Attention U-Net/DeepLabV3+; SegFormer là optional dependency.
- Load checkpoint an toàn `weights_only=True`, metadata check và strict state dict.
- ONNX Runtime semantic adapter dùng chung preprocessing/postprocessing.
- Tool benchmark runtime và tool export/validate ONNX.
- Provenance chứa model version, artifact role/checksum, runtime, device và preprocessing.

## Chất lượng LOSO semantic

Trung bình ba test fold D1/D2/D3, seed 42 từ metrics đi kèm checkpoint:

| Model | Weed IoU | Weed Dice | mIoU mọi lớp | mDice mọi lớp |
| --- | ---: | ---: | ---: | ---: |
| Attention U-Net | 0.5566 | 0.7104 | 0.7327 | 0.8331 |
| DeepLabV3+ R50 | 0.4625 | 0.6295 | 0.6420 | 0.7575 |
| SegFormer-B0 | **0.5914** | **0.7427** | **0.7510** | **0.8489** |

SegFormer đang là winner đánh giá, nhưng chưa được tự động nâng thành deployment model.

## Benchmark CPU

Ảnh RGB `640 x 640`, artifact D1, ba lần dự đoán, median; macOS CPU hiện tại:

| Model | Load (ms) | Inference median (ms) | Process peak delta (MB) |
| --- | ---: | ---: | ---: |
| Attention U-Net | 586.1 | 2145.8 | 3166.7 |
| DeepLabV3+ R50 | 1669.2 | 946.0 | 1438.0 |
| SegFormer-B0 | 2601.9 | **252.1** | **710.1** |

Đây là benchmark kỹ thuật một ảnh, không phải SLA phát hành. Số RAM là process
maximum RSS, bao gồm Python/framework và activation.

## Verification

| Kiểm tra | Kết quả |
| --- | --- |
| Strict checkpoint load | 3/3 semantic families passed |
| Tham số model | Khớp metadata train cho cả 3 model |
| Attention U-Net PyTorch golden | 100% pixel match |
| Attention U-Net ONNX golden | 100% pixel match |
| ONNX checker/runtime | Output `1 x 3 x 640 x 640`, passed |
| Checksum inventory | 9 semantic valid; 2 instance pending |
| Contract tests Phase 3 | 16/16 passed |
| Full test suite | 57/57 passed; package coverage 81% |
| Ruff / mypy / lockfile / diff check | Passed |
| Build và cài wheel ngoài source | Import và strict checkpoint load passed |

## Phần để mở

1. Chưa có deployment checkpoint semantic huấn luyện trên split cuối; LOSO chỉ phục vụ đánh giá.
2. ONNX proof được tạo trong thư mục tạm, chưa đăng ký artifact phát hành.
3. YOLOv8 và Mask R-CNN adapters cần checkpoint/config thật để khóa class index,
   preprocessing và postprocessing; contract instance đã sẵn sàng.
4. Benchmark GPU/Windows/Linux và peak RAM trong worker process thuộc packaging/job phase.
5. Tile/merge ảnh lớn, job queue và cancellation thuộc Phase 4.
