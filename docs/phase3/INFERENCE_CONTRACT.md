# Inference contract Phase 3

## Input convention

- `ImageInput.pixels`: `uint8`, shape `H x W x 3`.
- Caller phải khai báo `ColorSpace.RGB` hoặc `ColorSpace.BGR`; model luôn nhận RGB.
- Semantic preprocessing hiện tại: resize stretch bilinear về `640 x 640`, chia `255`,
  không mean/std normalization.
- Output luôn được chiếu lại về kích thước ảnh nguồn.

## Semantic output

`SemanticPrediction` có:

- `class_map`: `int32`, shape `H x W`.
- `probabilities`: `float32`, shape `C x H x W`, class axis đứng đầu.
- `target_masks`: mask bool cho output nghiệp vụ.
- `PredictionProvenance`: model ID/version, artifact role/checksum, runtime, device và
  fingerprint preprocessing.
- `latency_ms`: chỉ thời gian forward và postprocess logits.

Checkpoint semantic v7.2 có class order `background/crop/weed`. `crop` là lớp phụ
giúp semantic model phân biệt thực vật, **không dùng để đếm hoặc tạo instance ngô**.
`target_masks` của semantic chỉ được phép chứa `weed`.

## Instance output

`InstanceBatchPrediction` chứa các `InstancePrediction` với:

- class `maize2`, `maize4` hoặc `maize6`;
- confidence trong `[0, 1]`;
- bounding box theo `xyxy` pixel coordinates;
- mask bool đúng kích thước ảnh nguồn.

Weed bị cấm trong class map instance. Adapter YOLOv8/Mask R-CNN chỉ được kích hoạt
sau khi checkpoint và preprocessing thật được bổ sung vào registry.

## Runtime behavior

- Checkpoint được xác minh SHA-256 trước khi load.
- PyTorch load bằng `weights_only=True` và allowlist tối thiểu `TorchVersion`.
- State dict được load `strict=True`.
- Checkpoint metadata phải khớp family, class order, input size và color profile.
- Mọi lỗi public dùng exception code ổn định; caller không cần parse message.
