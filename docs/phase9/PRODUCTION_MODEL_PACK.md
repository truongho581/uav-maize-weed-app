# Bộ trọng số chính thức v7.2

Registry `models/model_inventory.json` dùng bộ trọng số cục bộ tại
`models/checkpoints/`. Các file nhị phân bị Git ignore, nhưng PyInstaller đóng gói
chúng cùng thư mục `models/`. Registry dùng đường dẫn tương đối từ project root và
xác minh SHA-256 trước khi nạp.

## Semantic ngô - cỏ

- Model mặc định: `segformer-b0-v72-maizemask-weedsgalore`.
- Artifact: `best_joint_seed_42` (`best.pth`), SHA-256
  `bc0a01f40f27f3cfe3b4f373c858c3aee59711fc8ac610e432218e0c401fceda`.
- Dataset: MaizeMask kết hợp WeedsGalore, seed 42, input `640 x 640`.
- Output nghiệp vụ: semantic đồng thời `crop` và `weed`; cỏ dại vẫn là mục tiêu chính.
- Test split: mIoU `0.6023`, crop IoU `0.6742`, weed IoU `0.5304`, weed cover
  correlation `0.8871`.

## Instance maize

- Checkpoint chính thức: `yolov8-seg-v72-instance`.
- Artifact: `best_fixed_seed_42` (`best.pt`), SHA-256
  `33744d8c12f8141b5bdd10e3fd61637f533c85ca2bf92d0a1f72fd457bad9a0d`.
- Class: `maize2`, `maize4`, `maize6`; weed không thuộc instance model.
- Protocol: fixed spatial-guard split, seed 42, input `640 x 640`.
- Test split: mask mAP `0.3249`, mask mAP50 `0.4783`, maize-region IoU `0.7997`.

Worker instance nạp checkpoint này qua Ultralytics, xác minh class map, áp score
`0.25`, mask `0.50`, NMS IoU `0.70` và tối đa `300` detections cho mỗi tile. Ảnh lớn
được chạy theo tile chồng lấp; các mask cùng lớp ở mép tile có IoU từ `0.70` trở lên
được hợp nhất trước khi xuất số cây, JSON, mask và overlay.

## Dùng với bản desktop đóng gói

Bundle mang theo `models/checkpoints/`, nên không phụ thuộc thư mục kết quả huấn luyện
bên ngoài. Khi cần thay model pack, có thể chỉ định một registry khác bằng biến môi
trường `UAV_CROP_MODEL_REGISTRY`.
