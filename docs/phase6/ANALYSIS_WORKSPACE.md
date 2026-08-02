# Phase 6 - Analysis workspace

## Contract nghiệp vụ

- `weed`: semantic segmentation duy nhất; xuất probability raster, binary mask và tỷ
  lệ che phủ.
- `maize`: instance segmentation; không bao giờ dùng semantic weed làm instance.
- YOLOv8 và Mask R-CNN chỉ được bật sau khi registry có checkpoint instance hợp lệ và
  instance worker được triển khai.

## Chạy semantic

1. Mở mission có ảnh, chọn `Phân tích`.
2. Chọn semantic model, checkpoint role, thiết bị, tile, overlap và ngưỡng cỏ dại.
3. Chọn `Chạy phân tích`; job được persist trước khi spawn worker process.
4. UI poll parent-process service; worker không truy cập Qt hoặc SQLite.
5. Job có thể hủy, chạy lại sau lỗi và được đánh dấu interrupted khi app khởi động lại.

Registry mặc định là `models/model_inventory.json`. Bản triển khai có thể trỏ tới model
pack ngoài bundle bằng:

```text
UAV_CROP_MODEL_REGISTRY=/absolute/path/to/model_inventory.json
```

Checkpoint được kiểm tra tồn tại và SHA-256 trước khi job chạy. Registry mặc định chỉ
công bố SegFormer-B0 joint MaizeMask + WeedsGalore cho semantic production.

## Result viewer

Viewer đọc artifact đã publish của job `completed` và có các layer semantic ngô - cỏ,
mặt nạ cỏ dại, xác suất cỏ dại và ảnh chồng lớp.

- `Gốc`: ảnh RGB đầu vào.
- `Weed mask`: mask semantic nhị phân màu đỏ.
- `Xác suất`: thang màu xanh lam, cyan, vàng, đỏ từ xác suất thấp tới cao.
- `Overlay`: mask cỏ dại trên ảnh gốc với opacity điều chỉnh được.

Inspector hiển thị model, kích thước, tỷ lệ cỏ dại, số tile và ảnh nguồn. Viewer từ
chối artifact sai shape thay vì resize ngầm làm sai kết quả.

## Nhúng vào host

`AnalysisWorkspaceService` và viewmodel không phụ thuộc host điều khiển drone. Host có
thể cung cấp implementation khác cho mission repository, model catalog hoặc job
controller rồi nhúng `AnalysisWorkspacePage`; worker vẫn là ranh giới process riêng.
