# Phase 5 - Screenshot Checklist

## Ma trận

| Viewport | 100% | 125% | 150% |
| --- | --- | --- | --- |
| 1366 x 768 | pass (macOS) | pass (macOS) | pass (macOS) |
| 1440 x 900 | pass (macOS) | pass (macOS) | pass (macOS) |
| 1920 x 1080 | pass (macOS) | pass (macOS) | pass (macOS) |

## Mỗi ảnh phải kiểm tra

- Không có text bị cắt, chồng lấn hoặc tràn khỏi button/table/header.
- Sidebar 220 px ổn định; vùng nội dung còn sử dụng được.
- Mission table giữ tên mission co giãn, các cột số đọc được.
- Overview hiển thị đủ ba drone và command chính trong viewport hoặc scroll hợp lý.
- Focus, hover, selected, disabled và error có khác biệt rõ.
- Màu status đi cùng text; contrast đủ đọc.
- Tooltip cho refresh, back và analysis disabled đúng ngữ cảnh.

## Hệ điều hành

- macOS: kiểm tra font fallback và phím `Cmd`.
- Windows: kiểm tra Segoe UI, scale 125/150% và đường dẫn AppData.
- Linux: kiểm tra Noto Sans/Arial fallback, XDG paths và platform plugin.

Phase 5 đã render đủ chín tổ hợp Overview và một Mission list trên macOS. `tools/verify_phase5_screenshots.py` kiểm tra kích thước, variance và vùng sidebar không bị blank. Windows/Linux cần được chạy lại trong CI hoặc máy build tương ứng trước bản phát hành.
