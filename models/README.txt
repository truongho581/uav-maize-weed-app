# Không commit checkpoint nhị phân vào repository.
# Checkpoint production cục bộ nằm trong models/checkpoints/ và được PyInstaller bundle.
# Chọn checkpoint tương thích từ giao diện hoặc khai báo qua model registry.
# model_inventory.json dùng schema v2 và đường dẫn artifact tương đối với project root.
# Semantic xuất đồng thời crop và weed; weed vẫn là mục tiêu nghiệp vụ chính.
# SegFormer-B0 joint MaizeMask + WeedsGalore seed 42 là semantic production duy nhất.
# YOLOv8-seg fixed seed 42 là checkpoint production cho maize instance (maize2/4/6).
# Mask R-CNN vẫn pending cho tới khi có checkpoint chính thức.
