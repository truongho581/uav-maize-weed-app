# Phase 7 - Geospatial contract

## Ba loại sản phẩm

| Loại | Độ chính xác được phép công bố | Nội dung |
| --- | --- | --- |
| `preview_mosaic` | `preview_only` | Contact sheet theo ba làn và sequence; luôn có watermark `NOT GEOREFERENCED` |
| `orthomosaic` | `georeferenced` | GeoTIFF có CRS và affine transform hợp lệ, do NodeODM hoặc nguồn ngoài tạo |
| `weed_heatmap` | `georeferenced` | Probability/mask semantic chiếu đúng lưới của orthomosaic nguồn |

Preview không có `GeoRasterMetadata` và không được dùng để suy ra vị trí thực địa.
Một raster chỉ được nhập là orthomosaic khi có cả CRS và transform không phải identity.

## Quy trình

1. Mission chứa đúng ba drone, ảnh được sắp theo drone/làn và `sequence_index`.
2. `Tạo preview` tạo contact sheet để kiểm tra thứ tự; không thực hiện ghép địa lý.
3. `Nhập GeoTIFF` kiểm tra CRS/transform rồi sao chép vào vùng dữ liệu do ứng dụng quản lý.
4. Khi cấu hình `UAV_CROP_NODEODM_URL`, `Chạy NodeODM` gửi toàn bộ ảnh có GPS tới
   NodeODM bằng PyODM và nhập `odm_orthophoto.tif` trả về.
5. Job weed semantic chạy trực tiếp trên orthomosaic. Probability và mask phải có cùng
   chiều rộng/cao với raster nguồn trước khi được xuất.
6. `Xuất heatmap` tạo GeoTIFF probability, GeoTIFF mask, PNG có thang xác suất,
   GeoJSON vùng vượt ngưỡng và valid-data mask.

NodeODM là dịch vụ ngoài, không được nhúng vào desktop bundle. URL có token chỉ dùng khi
kết nối; provenance loại bỏ query string để không ghi token xuống database.

## Raster và provenance

`GeoRasterMetadata` lưu:

- CRS, affine transform sáu hệ số, bounds, width/height, pixel resolution và nodata.
- Heatmap giữ nguyên CRS, transform, width và height của orthomosaic.
- GeoJSON được chuyển sang `EPSG:4326`; `source_crs` vẫn được ghi trong metadata collection.
- `source_product_id` và `source_job_id` liên kết heatmap với orthomosaic và job AI.
- Provenance ghi checksum orthomosaic, model/artifact, threshold, manifest checksum và
  đường dẫn các lớp dẫn xuất.

`valid-data-mask.tif` chỉ biểu diễn pixel có dữ liệu theo raster mask của orthomosaic.
Nó không phải confidence hình học, sai số GPS hay độ chính xác control point.

## Điều kiện từ chối

- Không chạy NodeODM nếu mission rỗng, ảnh thiếu GPS hoặc chưa cấu hình endpoint.
- Không nhận raster thiếu CRS/transform.
- Không xuất heatmap từ job chưa hoàn thành hoặc job không chạy trên orthomosaic đã chọn.
- Không xuất layer nếu kích thước prediction khác lưới orthomosaic.
- Không gán instance cho weed. Maize instance/density chỉ được thêm sau khi checkpoint
  instance và contract class tương ứng được đăng ký.

## Nguồn kỹ thuật

- [PyODM documentation](https://pyodm.readthedocs.io/en/stable/): client chính thức cho API NodeODM.
- [NodeODM](https://github.com/OpenDroneMap/NodeODM): API xử lý ảnh UAV của OpenDroneMap.
- [Rasterio quickstart](https://rasterio.readthedocs.io/en/stable/quickstart.html): CRS,
  affine transform và GeoTIFF profile.
