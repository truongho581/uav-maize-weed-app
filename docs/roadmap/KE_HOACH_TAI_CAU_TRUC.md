# Kế hoạch tái cấu trúc UAV Crop Analysis

## 1. Mục tiêu

Tái cấu trúc phần mềm hiện tại thành một sản phẩm có các đặc tính sau:

- Chạy độc lập trên Windows, Linux và macOS bằng bộ cài/bản đóng gói riêng cho từng hệ điều hành.
- Phần lõi phân tích không phụ thuộc giao diện và có thể được nhúng như một Python package hoặc gọi qua API cục bộ.
- Quản lý nhiệm vụ khảo sát gồm 03 drone, dữ liệu ảnh, flight log, metadata camera và kết quả theo không gian.
- Hỗ trợ nhiều mô hình AI: ngô dùng instance segmentation; cỏ dại dùng semantic segmentation.
- Có thể thêm model, camera, định dạng flight log, công cụ orthomosaic và giao thức drone mà không sửa phần lõi.
- Có quy trình build, kiểm thử, review và phát hành tái lập được.

Phạm vi ban đầu là xử lý dữ liệu sau bay và tích hợp đọc mission/telemetry. Điều khiển bay trực tiếp là adapter mở rộng, không đặt trong tiến trình AI và không được xem là chức năng an toàn bay cho đến khi qua kiểm thử mô phỏng và thực địa riêng.

## 2. Đánh giá hiện trạng

### Điểm có thể giữ lại

- Pipeline chia tile và ghép mask trong `tile_engine.py`.
- Cách phân biệt ngô instance và cỏ dại semantic.
- Các phép tính chỉ số trong `crop_processor.py` và `weed_processor.py` sau khi chuẩn hóa đơn vị/đầu vào.
- Model YOLO hiện tại và dữ liệu DJI làm baseline hồi quy.
- PyInstaller làm công cụ đóng gói giai đoạn đầu.

### Vấn đề cần xử lý

- `phan_tich_ui.py` đang chứa giao diện, orchestration, xử lý nền, AI, ghép ảnh và xuất kết quả; khó kiểm thử và mở rộng.
- `CropAICore` gắn trực tiếp với Ultralytics YOLO, chưa có contract chung cho semantic/instance model.
- Chưa có domain model cho mission, drone, ảnh, telemetry, camera profile và analysis job.
- Ghép nhiều ảnh bằng ORB/homography chỉ nên được gọi là preview mosaic; chưa phải orthomosaic có tọa độ.
- Chưa có persistence, migration dữ liệu, job recovery và provenance của model/kết quả.
- File requirements chưa khóa phiên bản; build script đang giả định đầu ra `.exe` của Windows.
- Chưa có unit test, integration test, golden dataset, CI và smoke test trên ba hệ điều hành.
- Cần rà soát giấy phép trước khi phát hành: PyQt5, Ultralytics và OpenDroneMap có điều kiện phân phối cần được xem xét.

## 3. Quyết định kiến trúc

### 3.1. Kiểu kiến trúc

Áp dụng **modular monolith theo ports and adapters**. Không tách microservice ở giai đoạn đầu; chỉ tách tiến trình đối với tác vụ nặng hoặc rủi ro cao.

```text
                         Desktop UI (PySide6)
                                  |
CLI / Python SDK -------- Application services -------- Local REST API
                                  |
                              Domain model
                                  |
          +-----------------------+-----------------------+
          |                       |                       |
     AI adapters             Data adapters          Integration adapters
  ONNX/PyTorch/YOLO       SQLite/files/EXIF       ODM/MAVSDK/QGC log
```

Quy tắc phụ thuộc:

- `domain` không import Qt, OpenCV, Torch, Ultralytics, ODM hay MAVSDK.
- `application` chỉ biết các interface/port và domain object.
- `adapters` hiện thực port cho framework/thư viện cụ thể.
- `desktop`, `cli` và `api` chỉ gọi application service, không gọi model trực tiếp.
- Tác vụ AI/orthomosaic chạy trong worker process để UI không treo và có thể hủy/retry.

### 3.2. Stack đề xuất

| Thành phần | Lựa chọn | Lý do |
| --- | --- | --- |
| Python | Python 3.11, quản lý bằng `pyproject.toml` | Tương thích tốt với hệ sinh thái AI và đóng gói |
| Desktop | PySide6 + Qt Widgets + Qt Model/View | Di chuyển dần từ PyQt5, chạy đa nền tảng, binding chính thức của Qt |
| Core contracts | Dataclass/Pydantic | Validate dữ liệu mission, API và model manifest |
| Persistence | SQLite + SQLAlchemy/Alembic | File cơ sở dữ liệu cục bộ, có migration và truy vấn rõ ràng |
| Inference phát hành | ONNX Runtime CPU mặc định | Runtime đa nền tảng, giảm coupling vào framework train |
| Inference phát triển | PyTorch/Ultralytics tùy chọn | Dùng checkpoint hiện có và benchmark/export model |
| Geospatial | Rasterio, PyProj, Shapely | GeoTIFF, hệ tọa độ và geometry; đóng thành optional feature |
| Orthomosaic | Adapter NodeODM/ODM tùy chọn | Dùng engine photogrammetry đã được kiểm chứng |
| Drone integration | MAVSDK adapter tùy chọn | Telemetry/mission qua API cấp cao của MAVLink |
| Plugin | Python entry points; thêm `pluggy` khi cần hook phức tạp | Plugin có version và được phát hiện độc lập |
| Test | pytest, pytest-qt, coverage | Test core, UI model và luồng desktop |
| Quality | Ruff, MyPy, pre-commit | Format, lint và type checking tái lập |
| Packaging | PyInstaller trước; đánh giá `pyside6-deploy` sau | Tận dụng spec hiện có và giảm thay đổi đồng thời |

Không đưa OpenDroneMap vào binary desktop ở bản đầu. Ứng dụng gọi một NodeODM/ODM do người dùng cài riêng hoặc server nội bộ. Cách này giảm kích thước bộ cài, giảm lỗi native dependency và cho phép thay backend photogrammetry.

### 3.3. Cấu trúc repository đích

```text
UAV_CropAnalysis/
  pyproject.toml
  uv.lock
  src/uav_crop_analysis/
    domain/
      missions.py
      assets.py
      observations.py
      jobs.py
      errors.py
    application/
      ports/
        inference.py
        repositories.py
        orthomosaic.py
        telemetry.py
      services/
        import_mission.py
        analyze_mission.py
        build_heatmap.py
        export_report.py
    adapters/
      inference/
        onnx_semantic.py
        onnx_instance.py
        ultralytics_instance.py
        torch_semantic.py
      storage/
        sqlite/
        filesystem.py
        exif.py
      geospatial/
        raster.py
        nodeodm.py
      drone/
        csv_log.py
        mavsdk.py
        qgc_plan.py
    workers/
      analysis_worker.py
      mosaic_worker.py
    interfaces/
      desktop/
        views/
        viewmodels/
        models/
        widgets/
        resources/
      api/
      cli/
    bootstrap.py
  tests/
    unit/
    integration/
    contract/
    e2e/
    golden/
  models/
    manifests/
  docs/
    architecture/
    design/
    operations/
  packaging/
    pyinstaller/
    windows/
    linux/
    macos/
  .github/workflows/
```

Trong quá trình chuyển đổi, file cũ vẫn chạy được qua một compatibility entry point. Chỉ xóa đường chạy cũ sau khi test hồi quy xác nhận kết quả mới tương đương.

## 4. Contract dữ liệu cốt lõi

### 4.1. Domain object

- `Mission`: ID, tên, thời gian, vùng khảo sát, CRS, cấu hình bay, trạng thái.
- `Drone`: ID trong mission, serial tùy chọn, vùng/dải được giao.
- `CameraProfile`: kích thước ảnh, intrinsics, distortion, chế độ zoom, nguồn hiệu chuẩn.
- `ImageAsset`: đường dẫn, checksum, drone ID, thời điểm chụp, GPS, altitude AGL, heading.
- `TelemetrySample`: thời gian, vị trí, attitude, chất lượng GPS.
- `AnalysisJob`: cấu hình pipeline, model versions, trạng thái, progress và lỗi.
- `Observation`: instance ngô hoặc thống kê semantic cỏ dại có provenance.
- `RasterLayer`: orthomosaic, crop mask, weed probability, heatmap và CRS/transform.

Mọi kết quả phải truy ngược được về `mission_id`, `drone_id`, `image_id`, model ID/version/checksum và cấu hình inference.

### 4.2. Model plugin contract

```text
SemanticSegmenter
  load(manifest)
  predict(image_or_tile) -> SemanticPrediction

InstanceSegmenter
  load(manifest)
  predict(image_or_tile) -> InstancePrediction[]
```

- Attention U-Net, DeepLabV3+ và SegFormer hiện thực `SemanticSegmenter` cho weed.
- YOLOv8-seg và Mask R-CNN hiện thực `InstanceSegmenter` cho maize/stage.
- `TilePipeline` không biết model framework; nó chỉ nhận prediction chuẩn hóa.
- Model manifest chứa task, class map, input size, preprocessing, output adapter, runtime, version và SHA-256.
- Model không tương thích class/schema phải bị từ chối trước khi chạy job.

### 4.3. API tích hợp

Ba bề mặt tích hợp dùng chung application service:

1. Python SDK cho phần mềm điều khiển viết bằng Python.
2. CLI cho automation và debug: `uav-crop import`, `analyze`, `export`, `serve`.
3. Local REST API phiên bản hóa `/api/v1` cho phần mềm khác ngôn ngữ; sự kiện tiến độ dùng WebSocket/SSE ở phase sau.

API không cho UI desktop truy cập trực tiếp SQLite hoặc model. Adapter MAVSDK ban đầu chỉ đọc telemetry/import mission; chức năng gửi lệnh bay phải nằm sau feature flag và safety gate riêng.

## 5. Thiết kế UI/UX đích

### 5.1. Nguồn tham khảo

- [QGroundControl](https://github.com/mavlink/qgroundcontrol): luồng mission, bản đồ, trạng thái nhiều phương tiện và cảnh báo vận hành.
- [WebODM](https://github.com/WebODM/WebODM): project/task, tiến độ xử lý dữ liệu UAV và kết quả orthophoto.
- [napari](https://github.com/napari/napari): viewer ảnh theo layer Image/Labels/Shapes và mô hình plugin.
- [UI UX Pro Max Skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill): checklist thiết kế, accessibility và consistency dành cho coding agent.
- [Google Stitch Skills](https://github.com/google-labs-code/stitch-skills): cách duy trì `DESIGN.md`, design token và validation giữa các màn hình.

Hai repo skill chỉ là công cụ tham khảo cho quy trình thiết kế/review. Không thêm chúng vào dependency của ứng dụng và không sinh UI tự động mà thiếu review con người.

### 5.2. Information architecture

```text
Mission list
  -> Mission workspace
       -> Overview
       -> Data (3 drone, ảnh, metadata, lỗi)
       -> Analysis (model, queue, progress)
       -> Map (orthomosaic, layers, heatmap)
       -> Report
Settings
  -> Model registry
  -> Camera profiles
  -> Integrations
  -> Compute and storage
```

Mission workspace dùng bố cục vận hành ổn định:

- Thanh trái: navigation ngắn, icon + tooltip.
- Thanh trên: mission hiện tại, trạng thái ba drone, job và cảnh báo.
- Vùng giữa: ảnh/bản đồ lớn; layer có bật/tắt, opacity và legend.
- Panel phải: thuộc tính đối tượng/ảnh/vùng đang chọn.
- Thanh dưới: job queue và log thu gọn; không để modal chặn tác vụ dài.

Không dùng dashboard nhiều card trang trí. Ưu tiên bảng, layer control, trạng thái rõ và thao tác hàng loạt. Màu không phải tín hiệu duy nhất; cảnh báo luôn có icon/text và hỗ trợ bàn phím.

### 5.3. Quy trình thiết kế cho mỗi màn hình

1. Viết user story và tiêu chí hoàn thành trong `docs/design/USER_FLOWS.md`.
2. Wireframe trạng thái bình thường, trống, loading, lỗi và dữ liệu một phần.
3. Cập nhật token trong `docs/design/DESIGN.md`: màu, spacing, typography, icon, focus/disabled.
4. Review bằng checklist UI/UX agent; quyết định cuối theo workflow vận hành của người dùng.
5. Implement bằng view + viewmodel + Qt model, không nhúng nghiệp vụ vào widget.
6. Kiểm tra screenshot ở 1366x768, 1440x900, 1920x1080; scale 100%, 125%, 150%.
7. Kiểm tra keyboard navigation, focus, tooltip, contrast, text dài tiếng Việt và job/error states.

## 6. Roadmap theo phase

Ước lượng dưới đây dành cho một lập trình viên, chưa gồm thời gian huấn luyện model và bay thu dữ liệu. Mỗi phase tạo một PR/commit series độc lập, có demo và có thể dừng mà phần mềm vẫn chạy.

### Phase 0 - Baseline và safety net (1-2 ngày)

Phạm vi:

- Chọn Python 3.11, tạo `pyproject.toml`, dependency groups và lockfile.
- Thêm Ruff, MyPy bước đầu, pytest và coverage.
- Kiểm kê dataset DJI và các checkpoint hiện có; ghi định dạng nhãn, class map, split train/val/test, framework và preprocessing tương ứng.
- Chọn một golden subset cố định từ tập test hiện có; lưu manifest/checksum thay vì đưa dữ liệu lớn hoặc dữ liệu nhạy cảm vào Git.
- Ghi baseline CSV, mask checksum/tolerance và ảnh kết quả từ code hiện tại.
- Gắn ID/version/checksum ban đầu cho Attention U-Net, DeepLabV3+, SegFormer, YOLOv8 và Mask R-CNN.
- Lập bảng license/dependency/model; ghi rõ Ultralytics/ODM chỉ là optional cho đến khi chốt quyền phân phối.

Kiểm tra:

- `pytest`, lint và import smoke test chạy trên máy phát triển.
- Chạy 5-10 ảnh golden và lưu report baseline về thời gian/RAM/kết quả.
- Review: baseline có tái lập được, class maize/weed không bị diễn giải sai.

Điều kiện qua phase: có test phát hiện thay đổi ngoài ý muốn khi bắt đầu di chuyển code.

### Phase 1 - Tạo skeleton và tách domain (3-4 ngày)

Phạm vi:

- Tạo `src` layout, domain object và error taxonomy.
- Tạo application service/port đầu tiên; chưa đổi UI.
- Bọc code cũ bằng compatibility adapter để `main.py` tiếp tục chạy.
- Chuẩn hóa logging, config path và app data path theo từng OS.

Kiểm tra:

- Unit test domain validation và đường dẫn Windows/Linux/macOS.
- Import test chứng minh `domain` không kéo Qt/Torch/OpenCV.
- Chạy lại golden test qua compatibility adapter.

Review: dependency direction, public API và naming domain.

### Phase 2 - Mission store và import dữ liệu 3 drone (4-6 ngày)

Phạm vi:

- SQLite schema, migration đầu tiên và repository ports.
- `mission.json`, camera profile, image asset, telemetry sample.
- Import ba thư mục drone, checksum ảnh, EXIF và CSV flight log.
- Đồng bộ ảnh-log theo timestamp, validator độ cao/GPS/thứ tự/ảnh trùng.

Kiểm tra:

- Contract test trên mission đủ dữ liệu, thiếu một drone, GPS lỗi, timestamp lệch và ảnh trùng.
- Migration test tạo/mở database mới và nâng version.
- Review report import: số ảnh mỗi drone, lỗi và coverage metadata.

Điều kiện qua phase: một mission đóng/mở lại vẫn giữ đúng toàn bộ metadata.

### Phase 3 - Model registry và AI adapters (5-8 ngày)

Phạm vi:

- Tạo semantic/instance contracts và prediction DTO chuẩn hóa.
- Adapter YOLOv8 hiện tại; adapter Mask R-CNN.
- Adapter Attention U-Net, DeepLabV3+, SegFormer theo checkpoint thực tế.
- Model manifest, class mapping, preprocessing và checksum.
- Export/validate ONNX; ONNX Runtime CPU là cấu hình đóng gói mặc định.

Kiểm tra:

- Contract test mọi adapter trả cùng schema, dtype, shape và coordinate convention.
- Golden test: mask/instance sau refactor nằm trong tolerance baseline.
- Benchmark theo model: Dice/mIoU cho weed; mask AP/count error cho maize; latency và peak RAM.
- Review riêng preprocessing/postprocessing vì đây là nơi dễ tạo sai khác âm thầm.

Điều kiện qua phase: đổi model bằng manifest/config mà không sửa UI hoặc pipeline.

### Phase 4 - Pipeline job và worker process (4-6 ngày)

Phạm vi:

- Tách tile, inference, merge, metric, artifact export thành các pipeline stage.
- Job state machine: queued/running/cancelled/failed/completed.
- Chạy AI trong worker process; progress, cancel, retry và lỗi có cấu trúc.
- Ghi provenance và artifact atomically để job lỗi không tạo kết quả giả hoàn chỉnh.

Kiểm tra:

- Test cancel/retry, file lỗi, model lỗi, hết bộ nhớ mô phỏng và app restart.
- So sánh kết quả single-process với worker process.
- Stress test mission nhiều ảnh; UI cũ vẫn phản hồi khi worker chạy.

Review: không swallow exception, không cập nhật UI từ worker thread/process trực tiếp.

### Phase 5 - PySide6 shell và design system (5-7 ngày)

Phạm vi:

- Chuyển PyQt5 sang PySide6, giữ Qt Widgets để giảm rủi ro.
- Tạo app shell, navigation, theme token, icon, typography và component states.
- Tách view/viewmodel/Qt model; màn Mission list và Overview đầu tiên.
- Tạo `DESIGN.md`, `USER_FLOWS.md` và screenshot review checklist.

Kiểm tra:

- pytest-qt cho navigation, command enable/disable và error state.
- Screenshot ba độ phân giải, ba mức scale; kiểm tra Windows/macOS/Linux.
- Keyboard/focus/tooltip và text tiếng Việt.

Review cùng người dùng: luồng mở mission, nhìn trạng thái và bắt đầu phân tích không quá ba bước chính.

### Phase 6 - Data workspace và analysis workspace (5-7 ngày)

Trạng thái: **đã thực hiện**. Phase 6.5 sau đó đã xóa hoàn toàn PyQt5 và các module
legacy ở project root; xem `docs/phase6_5/PHASE6_5_REVIEW.md`.

Phạm vi:

- Màn Data hiển thị ba drone, bảng ảnh, metadata và lỗi import.
- Màn Analysis chọn model semantic/instance, cấu hình và job queue.
- Image viewer dạng layer: original, maize instances/stages, weed probability/mask, overlay.
- Inspector và legend; giữ layout ổn định khi chuyển layer/ảnh.

Kiểm tra:

- E2E UI: import mission -> sửa mapping -> chạy -> cancel/retry -> mở kết quả.
- Test mission rỗng, một drone thiếu ảnh, model thiếu và disk gần đầy.
- Screenshot review và usability walkthrough bằng dữ liệu thật.

Điều kiện qua phase: toàn bộ chức năng phân tích hiện có chạy qua UI mới.

### Phase 7 - Geospatial, orthomosaic và heatmap (7-12 ngày)

Trạng thái: **đã thực hiện phần weed semantic và hạ tầng geospatial**; xem
`docs/phase7/PHASE7_REVIEW.md`. Maize density/stage chờ checkpoint instance như đã thống nhất;
control point/seam trên dữ liệu thật chờ mission ba drone và NodeODM triển khai.

Phạm vi:

- Tách rõ `preview mosaic` và `georeferenced orthomosaic`.
- NodeODM/ODM adapter; theo dõi task và nhập GeoTIFF/CRS/transform.
- Chiếu prediction lên orthomosaic; heatmap weed semantic, maize density/stage.
- Xuất GeoTIFF/GeoJSON/PNG có legend và confidence/data-quality layer.
- Fallback theo grid/GPS chỉ tạo spatial preview và phải gắn nhãn độ tin cậy.

Kiểm tra:

- Synthetic geospatial fixtures có tọa độ kỳ vọng.
- So sánh control points/extent/CRS với kết quả ODM tham chiếu.
- Kiểm tra seam, vùng không dữ liệu, ảnh trùng và ranh giới giữa ba drone.
- Review trực quan trên một mission đầy đủ và một mission thiếu dữ liệu.

Điều kiện qua phase: heatmap có thể truy ngược đến ảnh/metadata và không được gọi là địa lý chính xác khi thiếu georeference.

### Phase 8 - Report và export (3-5 ngày)

Trạng thái: **đã thực hiện** với JSON schema 1, CSV chi tiết, HTML tự chứa và checksum
manifest; xem `docs/phase8/PHASE8_REVIEW.md`. Excel/PDF không thêm dependency riêng vì
HTML có thể in PDF và CSV mở trực tiếp bằng Excel.

Phạm vi:

- Dashboard tổng hợp mission và từng drone.
- CSV/Excel/PDF hoặc HTML report; GeoTIFF/GeoJSON cho hệ GIS.
- Report chứa model version, nguồn camera, GSD, chất lượng dữ liệu và giới hạn kết quả.
- Template report có version để không phá backward compatibility.

Kiểm tra:

- Snapshot/contract test schema export.
- Mở artifact bằng công cụ độc lập; kiểm tra Unicode và đường dẫn Windows.
- Review số liệu tổng có khớp chi tiết ảnh và layer địa lý.

### Phase 9 - SDK/API và adapter phần mềm điều khiển (5-8 ngày)

Trạng thái: **đã thực hiện** với SDK schema 1/package 0.2.0, CLI `uav-crop`, REST
`/api/v1`, QGC plan/log reader, MAVSDK read-only và ba stream mô phỏng; xem
`docs/phase9/PHASE9_REVIEW.md`.

Phạm vi:

- Public Python SDK và CLI ổn định.
- Local REST API `/api/v1` cho mission/job/result; health/version/capabilities endpoint.
- QGroundControl plan/log importer.
- MAVSDK adapter chỉ đọc connection/telemetry và mission trước; map `system_id` sang `drone_id`.
- Demo tích hợp ba drone bằng PX4/ArduPilot SITL hoặc ba telemetry stream mô phỏng.

Kiểm tra:

- API contract test và backward compatibility test.
- Mất kết nối, reconnect, dữ liệu đến sai thứ tự và trùng system ID.
- Test không có adapter drone: desktop/offline analysis vẫn chạy bình thường.
- Safety review trước mọi chức năng gửi lệnh; mặc định read-only.

Điều kiện qua phase: phần mềm điều khiển bên ngoài có thể tạo/import mission, theo dõi job và lấy kết quả mà không import Qt.

### Phase 10 - Đóng gói và CI đa nền tảng (5-8 ngày)

Phạm vi:

- PyInstaller spec theo platform; model pack tách khỏi app core nếu quá lớn.
- GitHub Actions matrix: Windows x64, Ubuntu x64, macOS arm64/x64 theo thiết bị hỗ trợ.
- Artifact: Windows installer/portable, Linux AppImage hoặc tarball, macOS `.app`/`.dmg`.
- CPU build là baseline; CUDA/DirectML/CoreML là variant sau khi CPU ổn định.
- App data/model/cache nằm đúng thư mục người dùng, không ghi vào bundle read-only.

Kiểm tra:

- Cài trên máy sạch/VM; mở app, import mission mẫu, chạy inference nhỏ, export kết quả.
- Kiểm tra model/artifact path có Unicode và khoảng trắng.
- Scan dependency/license và antivirus false-positive cơ bản.
- macOS signing/notarization và Windows code signing là release gate khi phân phối ngoài nhóm nghiên cứu.

Lưu ý: PyInstaller không cross-compile; mỗi artifact phải build trên runner đúng hệ điều hành.

### Phase 11 - Hardening và nghiệm thu (5-8 ngày)

Phạm vi:

- Performance profiling, memory leak, disk quota và recovery.
- Security: validate file/path, model checksum, API bind localhost mặc định.
- User manual, operator checklist, troubleshooting và architecture decision records.
- Demo nghiệm thu: mission ba drone, dữ liệu 10-20 m, maize instance, weed semantic, orthomosaic/heatmap và report.

Kiểm tra:

- Regression toàn bộ golden dataset và benchmark đã chốt.
- Soak test nhiều mission liên tiếp.
- Cross-platform acceptance checklist và restore từ job lỗi.
- Review cuối theo requirement traceability matrix.

Điều kiện hoàn tất: không còn lỗi blocker/high, package ba OS vượt smoke test, tài liệu và demo tái lập được.

## 7. Quality gate chung sau mỗi phase

Mỗi phase chỉ được đóng khi đủ các mục sau:

1. Acceptance criteria của phase đã được demo bằng dữ liệu cụ thể.
2. Unit/integration/golden tests liên quan đều qua; coverage phần code mới đạt ngưỡng thống nhất của dự án.
3. Lint/type check qua; không có dependency ngược kiến trúc.
4. Review code tập trung vào correctness, failure modes, performance và migration.
5. UI thay đổi phải có screenshot và trạng thái empty/loading/error/partial.
6. Docs/API/schema/migration được cập nhật cùng code.
7. Không làm sai baseline AI ngoài tolerance nếu không có benchmark và phê duyệt thay đổi.
8. Git diff không chứa model/dataset/binary lớn hoặc dữ liệu nhạy cảm ngoài chủ đích.

## 8. Chiến lược branch và phát hành

- Mỗi phase chia thành PR nhỏ theo vertical slice, không tạo một nhánh refactor kéo dài nhiều tuần.
- Feature flag cho UI mới, worker mới, ODM và MAVSDK để có đường rollback.
- Version theo SemVer cho Python SDK/API; schema database có migration tuần tự.
- Release channel: `dev` -> `preview` -> `stable`.
- Model version độc lập app version; model manifest và checksum đi cùng report.
- Binary không dùng chung ba OS: build và kiểm thử native trên từng runner.

## 9. Thứ tự ưu tiên và mốc bàn giao

| Mốc | Phase | Giá trị bàn giao |
| --- | --- | --- |
| M1 - Core ổn định | 0-4 | Core tách UI, mission store, nhiều AI backend, job worker |
| M2 - Desktop sử dụng được | 5-6 | UI mới thay đầy đủ luồng phân tích hiện tại |
| M3 - Kết quả theo không gian | 7-8 | Orthomosaic, heatmap địa lý và report |
| M4 - Module tích hợp | 9 | SDK/API và demo ba nguồn drone mô phỏng/SITL |
| M5 - Release | 10-11 | Package ba OS, hardening và bộ demo nghiệm thu |

Dataset và checkpoint của dự án đã có sẵn, vì vậy roadmap không bao gồm thời gian thu thập dữ liệu, gán nhãn hoặc huấn luyện từ đầu. Ước lượng tổng cho một lập trình viên là khoảng 10-14 tuần, phụ thuộc chủ yếu vào độ tương thích checkpoint, orthomosaic và build native trên ba hệ điều hành. Nên nghiệm thu nội bộ ở từng mốc thay vì đợi đến cuối toàn bộ roadmap.

## 10. Repo/tài liệu tham khảo kỹ thuật

- [Qt for Python/PySide6](https://doc.qt.io/qtforpython-6/): binding Qt chính thức, Model/View và deployment.
- [PyInstaller](https://github.com/pyinstaller/pyinstaller): đóng gói Python cho Windows, Linux và macOS; build native theo OS.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime): inference đa nền tảng và execution provider theo phần cứng.
- [pluggy](https://github.com/pytest-dev/pluggy): plugin hook tối giản, phù hợp khi entry points không đủ.
- [OpenDroneMap/ODM](https://github.com/OpenDroneMap/ODM) và [NodeODM](https://github.com/OpenDroneMap/NodeODM): orthomosaic/GeoTIFF và API xử lý ảnh UAV.
- [MAVSDK-Python](https://github.com/mavlink/MAVSDK-Python): client Python qua gRPC cho MAVLink telemetry/mission.
- [QGroundControl](https://github.com/mavlink/qgroundcontrol): tham khảo mission planning, multi-vehicle và UX vận hành.
- [napari architecture](https://napari.org/stable/developers/architecture/index.html): tách model/event/Qt và layer-based scientific viewer.
