# Phase 1 - Kien truc loi

## Dependency direction

```text
Desktop / drone-control host
            |
         adapters
            |
       application
            |
          domain
```

- `domain` chi dung Python standard library va error taxonomy chung.
- `application` dieu phoi domain thong qua `Protocol`; khong biet SQLite, Qt, Torch hay OpenCV.
- `adapters` ket noi persistence, AI runtime va desktop cu vao application boundary.
- `infrastructure` quan ly config, app paths va logging; khong thuc hien I/O khi import.
- UI hoac phan mem dieu khien drone goi application service, khong goi truc tiep persistence.

## Package layout

```text
src/uav_crop_analysis/
  domain/          Mission, drone assignment, flight profile, invariant
  application/     Use case va repository port
  adapters/        In-memory repository va legacy compatibility
  infrastructure/  Paths, environment config va logging
  resources/       Qt Designer resource duoc dong goi trong wheel
  errors.py        Error taxonomy on dinh cho caller
```

Sau Phase 1, cac module phang `ai_core.py`, `crop_processor.py`, `tile_engine.py`,
`weed_processor.py` va desktop PyQt5 van duoc giu de tuong thich. Code moi khong
duoc import nguoc tu cac module nay.

## Public contracts

### Domain

- `MissionId`, `DroneId`: value object bat buoc co gia tri.
- `FlightProfile`: do cao 10-20 m, gimbal mac dinh -90 do, forward overlap 75%, side overlap 65%, stop-and-capture.
- `DroneAssignment`: gan drone vao lane song song `0..2`.
- `SurveyMission`: dung dung 3 drone, ID drone duy nhat, lane duy nhat va timestamp co timezone.

### Application

- `MissionRepository`: `add()` va `get()`; SQLite se implement port nay o Phase 2.
- `CreateSurveyMissionCommand`: input DTO khong phu thuoc UI.
- `CreateSurveyMission.execute()`: tao va luu mission, bao loi neu trung ID.

### Runtime

- `resolve_app_paths()`: duong dan data/config/cache/log theo Windows, macOS va Linux/XDG.
- `AppConfig.from_environment()`: doc config co validate, hien tai ho tro `UAV_CROP_LOG_LEVEL`.
- `configure_logging()`: rotating UTF-8 file log, 5 MiB x 3 backup.

## Error taxonomy

| Error | Y nghia cho caller |
| --- | --- |
| `DomainValidationError` | Du lieu mission/flight profile khong hop le |
| `MissionAlreadyExistsError` | Mission ID da ton tai |
| `ConfigurationError` | OS hoac environment config khong hop le |
| `CheckpointNotConfiguredError` | Chua chon checkpoint hoac file khong ton tai |
| `DependencyUnavailableError` | Runtime tuy chon nhu desktop/AI chua san sang |

Moi error co `code` va `context`; caller khong can parse chuoi message.

## Compatibility boundary

- `LegacyAnalysisAdapter` chi import `ai_core` khi `analyze_bgr()` duoc goi.
- `launch_legacy_desktop()` chi import Qt desktop khi khoi dong ung dung.
- `main.py` van chay truc tiep; console script moi di qua compatibility adapter.
- Checkpoint khong duoc dong goi mac dinh. UI khoi dong o trang thai `Chua chon model`.

## Phase 2 extension points

- SQLite repository implement `MissionRepository`.
- Them `ImageAsset`, `TelemetrySample`, camera profile va import report.
- Them mission manifest schema/version va migration.
- Them adapter import ba thu muc drone, EXIF va flight log theo timestamp.
