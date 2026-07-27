# Review Phase 1 - Skeleton va domain boundary

Ngay review: 2026-07-27.

## Ket luan gate

**Dat dieu kien bat dau Phase 2.** Package moi co dependency direction ro rang, domain khong keo UI/AI runtime, desktop cu van khoi dong khong checkpoint mac dinh, va wheel chua resource Qt can thiet.

AI golden regression van de mo dung chu dich cho den khi co checkpoint instance v7.2 chinh thuc; khong dung lai checkpoint legacy da loai.

## Da hoan thanh

- Tao `src/uav_crop_analysis` voi cac layer domain, application, adapters, infrastructure va resources.
- Tao error taxonomy co `code` va structured `context`.
- Khoa invariant mission gom dung 3 drone, ba lane song song va flight profile 10-20 m.
- Tao `MissionRepository` port, create-mission service va in-memory adapter.
- Chuan hoa app data/config/cache/log paths cho Windows, macOS va Linux.
- Them environment config va rotating file logging.
- Them legacy AI/desktop adapter voi lazy import.
- Chuyen Qt `.ui` thanh package resource va doi console entrypoint qua adapter.

## Ket qua kiem tra

| Kiem tra | Ket qua |
| --- | --- |
| `python -m pytest` | 28/28 passed |
| Coverage package moi | 90% |
| Domain import boundary | Khong load PyQt5, Torch, OpenCV, NumPy, Ultralytics |
| `python -m ruff check .` | Passed |
| `python -m mypy` | Passed, 29 source files |
| Editable install | Passed |
| Wheel build | Passed |
| Wheel install ngoai source tree | Passed |
| Desktop offscreen tu wheel | Passed; resource `.ui` ton tai, model mac dinh la `None` |

## Review notes

1. `main.py` va `phan_tich_ui.py` van la compatibility surface PyQt5; MyPy bo qua import body cua `main` de no typing dong khong lam mo gate code moi.
2. Wheel hien la Python distribution smoke test, chua phai native installer Windows/macOS/Linux.
3. In-memory repository chi phuc vu test/prototype; SQLite migration va transaction nam o Phase 2.
4. Chua co schema telemetry thuc te cua bo dieu khien drone; importer Phase 2 can sample log de khoa mapping timestamp/GPS/do cao.
5. AI adapters chinh thuc va golden mask nam o Phase 3 sau khi co checkpoint deployment.

## Dau vao cho Phase 2

- Mot file log mau tu flight controller, kem ten cot va don vi timestamp/GPS/do cao.
- Cau truc thu muc anh thuc te cua ba drone, neu da co.
- Quy tac gan `drone_id` thuc te: serial, callsign hay ten thu muc.
