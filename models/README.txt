# Không commit checkpoint nhị phân vào repository.
# Chọn checkpoint tương thích từ giao diện hoặc khai báo qua model registry.
# model_inventory.json dùng schema v2 và đường dẫn artifact tương đối với project root.
# Semantic chỉ xuất weed cho nghiệp vụ; class crop trong checkpoint là lớp phụ.
# Hai model instance giữ trạng thái pending cho tới khi có checkpoint chính thức.
