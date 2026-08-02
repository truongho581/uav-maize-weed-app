# Phase 0 - Dependency and license audit

This is an engineering inventory, not legal advice. License terms must be
reviewed again before distributing binaries outside the research team.

| Component | Current/Planned use | License concern | Phase 0 decision |
| --- | --- | --- | --- |
| PyQt5 | Current desktop UI | Installed package reports GPLv3/commercial terms | Keep only for compatibility; migrate to PySide6 before release |
| PySide6 | Planned desktop UI | LGPLv3/GPLv3/commercial; dynamic-link and notice obligations | Adopt in Phase 5 after packaging proof |
| Ultralytics | Current YOLOv8 adapter | AGPL-3.0/enterprise terms require distribution review | Optional development adapter; do not decide product license implicitly |
| PyTorch/Torchvision | Training and optional inference | Permissive upstream license; retain notices | Keep optional |
| ONNX Runtime | Planned release inference | MIT | Preferred packaged inference runtime |
| Hugging Face Transformers | Optional SegFormer inference | Apache-2.0 | Optional semantic adapter; retain notices |
| Vendored DeepLabV3+ code | Packaged checkpoint-compatible architecture | MIT attribution in source | Retain upstream header and license notice before distribution |
| OpenCV | Image processing | Apache-2.0 | Keep; retain notices |
| NumPy/Pandas/Pillow | Core data/image processing | Permissive licenses with notices | Keep |
| ODM/NodeODM | Optional orthomosaic backend | AGPL-3.0 and large native dependency surface | Pull official container at runtime; do not bundle or modify the image |
| MAVSDK | Optional telemetry/mission adapter | BSD-3-Clause | Keep optional |
| PyInstaller | Packaging | GPL with bootloader exception; review bundled dependency licenses | Keep for initial native builds |
| Lucide Icons 1.27.0 | Bundled SVG icons for the desktop UI | ISC; selected SVG files and license text redistributed | Keep license at `src/uav_crop_analysis/resources/icons/LUCIDE_LICENSE.txt` |

## Open decisions

- Choose the distribution license for this repository.
- Confirm whether the final application is research-only, open source, or distributed as a closed binary.
- Confirm rights to redistribute each trained checkpoint and any pretrained backbone.
- Generate a third-party notices file from the locked release environment.
- Re-run the audit after replacing PyQt5 and after adding geospatial dependencies.
