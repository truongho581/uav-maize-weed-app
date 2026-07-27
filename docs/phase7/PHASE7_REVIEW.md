# Review Phase 7 - Geospatial, orthomosaic và heatmap

Ngày review: 2026-07-27.

## Đã hoàn thành

- Thêm domain contract cho preview, orthomosaic, weed heatmap và raster metadata.
- SQLite migration v3 lưu spatial product, nguồn dẫn xuất và provenance.
- Preview ba làn theo sequence có watermark bắt buộc, không công bố georeference.
- Adapter Rasterio kiểm tra/ghi GeoTIFF; adapter PyODM chạy NodeODM ngoài ứng dụng.
- Cho phép nhập orthomosaic GeoTIFF đã có để không phụ thuộc NodeODM trong desktop.
- Chạy weed semantic trực tiếp trên orthomosaic qua pipeline/job Phase 4.
- Xuất probability/mask/valid-data GeoTIFF, risk GeoJSON EPSG:4326 và PNG heatmap có legend.
- Trang `Không gian` có product table, raster viewer, CRS/bounds/resolution/provenance,
  thao tác nền và trạng thái NodeODM/GPS.
- PyInstaller spec đã khai báo adapter geospatial; Rasterio/PyODM là dependency khóa phiên bản.

## Kiểm tra

- Synthetic fixture `EPSG:32648` xác minh CRS, transform, extent, resolution và dimensions.
- Raster thiếu CRS/identity transform bị từ chối.
- Heatmap và valid-data mask giữ nguyên grid của orthomosaic; GeoJSON chuyển sang WGS84.
- Fake NodeODM task kiểm tra upload/status/download, task provenance và không lộ token.
- pytest-qt kiểm tra preview/georeference badge, enable/disable command, signal analysis/export
  và controller chạy ngoài UI thread.
- Screenshot review tại 1366x768, 1440x900 và 1920x1080; script kiểm tra kích thước,
  blank render và vùng raster viewer.
- Wheel có 80 entry, chứa package geospatial và không có module legacy. Bundle macOS
  727 MB đã khởi động từ `HOME` sạch, tạo SQLite schema v3 và application log.

## Giới hạn có chủ ý

- Chưa nghiệm thu control point/seam bằng mission bay thật vì cấu trúc ảnh ba drone và
  NodeODM endpoint thực tế chưa được cung cấp. Đây là bước kiểm tra dữ liệu triển khai,
  không phải lý do để gán độ chính xác cho preview.
- Maize density/stage geospatial chưa bật vì checkpoint instance sẽ được bổ sung sau.
  Weed vẫn chỉ là semantic theo yêu cầu đã chốt.
- Valid-data mask không đo sai số hình học. Khi cần GCP/RTK accuracy phải bổ sung quality
  metric từ report ODM thay vì diễn giải mask này thành confidence.
- Build native cần được chạy lại trên Windows và Linux trước phát hành; vòng hiện tại
  kiểm tra source/wheel/frozen app trên macOS.

## Kết luận

Luồng geospatial offline đã hoàn chỉnh và có thể nhúng: preview kiểm tra thứ tự, nhận/tạo
orthomosaic, chạy semantic, xuất heatmap có georeference và truy vết nguồn. Điều kiện review
trên mission thật được giữ mở cho tới khi người dùng cung cấp layout ảnh và NodeODM/data thực.
