# Phase 0 - Kiểm kê dataset

## Dataset chuẩn

- ID: `maizemask-v7.2`.
- Nguồn ảnh: DJI Mini 4K FC7703 RGB.
- Vị trí ngoài repository: `../agriculture_drone_prj/src_data/maize_mask_7.2.coco_standard_split_spatial_guard`.
- Định dạng: COCO instance/segmentation JSON, ảnh PNG 640x640.
- Chiến lược chia: standard split có spatial guard.

| Split | Ảnh | Annotation |
| --- | ---: | ---: |
| Train | 233 | 8.425 |
| Validation | 48 | 2.483 |
| Test | 50 | 2.115 |
| Tổng | 331 | 13.023 |

## Hợp đồng nhãn

| COCO ID | Tên | Cách dùng trong phần mềm |
| ---: | --- | --- |
| 1 | `maize-mask-7-2` | Metadata/category gốc; không phải class đầu ra triển khai |
| 2 | `maize-u` | Vùng ngô semantic; bỏ qua khi đánh giá instance |
| 3 | `maize2` | Instance ngô giai đoạn 2 lá |
| 4 | `maize4` | Instance ngô giai đoạn 4 lá |
| 5 | `maize6` | Instance ngô giai đoạn 6 lá |
| 6 | `weed` | Semantic segmentation; không đếm từng cá thể cỏ |

## Nguyên tắc sử dụng

- Ngô được xử lý theo instance để đếm cây và phân loại giai đoạn.
- Cỏ dại được xử lý theo semantic mask để tính diện tích, mật độ và heatmap.
- Golden subset chỉ lưu tên file và SHA-256 trong Git; ảnh vẫn ở dataset ngoài repository.
- Không dùng checkpoint LOSO để báo cáo kết quả triển khai trên chính domain test tương ứng.
