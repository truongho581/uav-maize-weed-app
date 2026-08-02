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
directory. Bản đóng gói chỉ giữ checkpoint production; checkpoint LOSO không còn được đăng ký. Manifest
`segformer-b0-v72-maizemask-weedsgalore` trỏ tới checkpoint chính thức và có status
`production_default`, nên được chọn trước trong danh mục semantic khi file có mặt.

Ví dụ nạp semantic model mà không sửa UI/pipeline:

```python
from uav_crop_analysis.inference import ModelRegistry, SegmenterFactory

registry = ModelRegistry.from_file("models/model_inventory.json")
factory = SegmenterFactory(registry)
segmenter = factory.load_semantic(
    "segformer-b0-v72-maizemask-weedsgalore",
    "best_joint_seed_42",
    device="cpu",
)
```

YOLOv8-seg fixed split có artifact `best_fixed_seed_42`, checksum và status
`production_default`. Factory nạp checkpoint qua Ultralytics, sau đó bắt buộc đối
chiếu class order `maize2/maize4/maize6` với registry. Mask R-CNN vẫn chưa có
checkpoint nên `resolve()` trả `model_unavailable`.

## ONNX

Export và validation:

```bash
python tools/export_semantic_onnx.py \
  segformer-b0-v72-maizemask-weedsgalore best_joint_seed_42 output.onnx
```

Tool kiểm `onnx.checker`, chạy một forward pass bằng ONNX Runtime và in SHA-256 cùng
shape để đưa artifact đã duyệt trở lại registry. Artifact thử nghiệm không được xem
là deployment model nếu chưa có quyết định chọn model/fold.
