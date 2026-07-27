# Model registry schema v2

Registry chính: `models/model_inventory.json`.

Mỗi model khai báo:

- ID, version, family, task và trạng thái;
- class map và `target_classes` nghiệp vụ;
- input size và dataset version;
- runtime cùng output adapter;
- preprocessing đầy đủ;
- từng artifact gồm role, path, format và SHA-256.

Đường dẫn artifact được resolve từ `artifact_root`, không phụ thuộc current working
directory. Các checkpoint LOSO giữ role riêng theo fold; phần mềm không tự chọn một
fold làm deployment model.

Ví dụ nạp semantic model mà không sửa UI/pipeline:

```python
from uav_crop_analysis.inference import ModelRegistry, SegmenterFactory

registry = ModelRegistry.from_file("models/model_inventory.json")
factory = SegmenterFactory(registry)
segmenter = factory.load_semantic(
    "segformer-b0-v72-loso",
    "best_test_D1_seed_42",
    device="cpu",
)
```

Instance entries hiện có manifest nhưng không có artifact. `resolve()` sẽ trả lỗi
`model_unavailable` cho tới khi checkpoint được đăng ký.

## ONNX

Export và validation:

```bash
python tools/export_semantic_onnx.py \
  attention-unet-v72-loso best_test_D1_seed_42 output.onnx
```

Tool kiểm `onnx.checker`, chạy một forward pass bằng ONNX Runtime và in SHA-256 cùng
shape để đưa artifact đã duyệt trở lại registry. Artifact thử nghiệm không được xem
là deployment model nếu chưa có quyết định chọn model/fold.
