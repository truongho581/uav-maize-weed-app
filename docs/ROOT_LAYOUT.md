# Tổ chức repository

Các tệp nguồn ở root được giới hạn cho entry point và cấu hình đóng gói:

- `main.py`: entry point tương thích cho ứng dụng desktop.
- `pyproject.toml`, `uv.lock`, `requirements.txt`, `requirements-dev.lock`: dependency và lockfile.
- `uav_analysis.spec`: cấu hình PyInstaller.
- `README.md`: điểm vào tài liệu.

Mã nguồn sống trong `src/`; kiểm thử ở `tests/`; tool phát triển ở `tools/`. Mọi tài liệu dự án
nằm trong `docs/`, gồm yêu cầu ở `requirements/`, roadmap ở `roadmap/`, phân tích hiện trạng ở
`analysis/` và tài liệu triển khai theo từng `phase*/`.

`Báo cáo nghiệm thu CN2025/` là nguồn tài liệu nghiệm thu do dự án cung cấp, không phải output
của build. Các thư mục `build/`, `dist/`, cache, virtual environment, package metadata và model
checkpoint là artifact cục bộ; chúng được Git ignore.
