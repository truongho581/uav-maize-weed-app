# Analysis artifact contract

Each attempt is written under:

```text
<output_root>/<job_id>/attempt-0001/
  <image_id>.weed_probability.npy
  <image_id>.weed_mask.png
  summary.json
  manifest.json
  COMPLETED.json
```

During processing the directory name starts with `.attempt-...`. Only `os.replace()`
publishes it as `attempt-NNNN`, on the same filesystem, after all files and completion
metadata have been written.

## Raster conventions

- Weed probability: NumPy `float32`, shape `H x W`, range `[0, 1]`.
- Weed mask: grayscale PNG, values `0` and `255`, source-image coordinates.
- Overlapping tiles are merged from probabilities with center-weighted blending.
- Threshold is recorded in `manifest.json`; default is `0.5`.
- Semantic crop output is not exported as a maize result.

## Provenance

`manifest.json` records:

- mission, job and attempt IDs;
- model ID and artifact role;
- model artifact SHA-256 and version through prediction provenance;
- runtime, device and preprocessing fingerprint;
- tile size, overlap and weed threshold;
- relative artifact paths, sizes and SHA-256 values.

`COMPLETED.json` contains the SHA-256 of `manifest.json`. Its presence distinguishes a
published result from an interrupted staging directory.

Each image summary contains dimensions, tile count, weed pixels, coverage percentage
and accumulated model inference latency. Geospatial projection and orthomosaic-level
heatmaps remain a later phase.
