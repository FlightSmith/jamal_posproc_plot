# v25.9 validation — 2026-09-28

Implementation of items 1–6, reviewed and approved by the user for commit and push.
v25.8.1 at 16fa8de is the previous approved release. Multi-element item 7 and the
portable executable/offline Plotly work remain unimplemented.

## Automated checks

Command from repository root:

```text
python -B -m unittest discover -s jamal_dashboard -p "test_*.py" -v
```

Result: **55 tests passed**. The suite includes Python compilation and generated
launcher/dashboard JavaScript syntax checks with Node.js.

- All 38 prior tests passed before distribution changes (the residual-range-only
  edit was already present). Historical force-derived expectations were then
  updated only where the user explicitly replaced the data source/calculation.
- Analytical closed-contour pressure checks: uniform pressure cancellation,
  known normal force, linear pressure-gradient force from enclosed area, reversed
  traversal, reversed loading, reference-pressure shifts, and ALPHA projection.
- Independent upper/lower quadrature on original fixture pressure coefficients;
  all original fixture checksums retained. Original files were not converted.
- Default absolute-pressure conversion and explicit legacy Cp; missing p/q;
  changing infout metadata with raw-cache reuse; ignored malformed/deleted/extra
  total_force files; missing states and geometry; unresolved contour rejection.
- Interpolation: exact samples, unsorted infout states, ALPHA and ADF CLS targets,
  distinct upper/lower grids, a 3,073-point union grid, no extrapolation, ambiguous
  stall/plateau crossings, duplicate alpha/stations, missing data, changed geometry,
  reference pressure/flow consistency, nonzero beta and unavailable load retention.
- Local/canted VTAIL geometry retains Cp but omits unsupported body loads; direct
  mathematical contour tests do not claim to validate 3D tail lift.
- Protected static-margin/moment-transfer source and numerical tests, Fluent
  subblock parsing, drag-rise, Delta interpolation, cache reuse and report rollback.
- Staging uses ordinary directory creation with inherited permissions; collision
  and cleanup checks pass. Real affected network-share confirmation remains pending.

## Browser checks

Generated a separate WING pressure-format test copy using p_local=p+qdin*Cp and
left the source fixtures untouched. Opened the generated standalone report locally.

- All nine station plots rendered with separate upper/lower traces, shared color,
  solid per-polar styling in Auto mode, and one legend entry per source.
- Two-polars ALPHA=2.6: both reconstructed from states 2/3 with weights 0.3/0.8.
- Two-polars CLS=0.5: POLAR-001 alpha=2.6338028169 (weight 0.3169014085),
  POLAR-002 alpha=2.2902633190 (weight 0.6451316595).
- Out-of-range CLS gave an explicit explanation; recorded data was not substituted.
- Manual Cp limits -3..1 produced identical inverted ticks on all nine panels;
  invalid limits showed a message and automatic fallback. Cp expansion opened.
- Target, overlays and manual limits restored after regenerating/reloading.
- Convergence residual panels rendered decade ticks from 1e-9 through 1e+0.
- No browser error/warning logs were reported during these checks.

## Limits requiring real-data review

Pressure and geometry must have matching samples/order. Load integration currently
supports single-element contours with two monotone X branches and confirmed X aft /
ordinate up coordinates, BETA=0, and constant reference flow. Pressure-only forces
exclude viscous shear, so they need not equal old total-force or global ADF loads.
The original synthetic VTAIL uses local normals and requires a future explicit
3D coordinate/span transformation. No wing/flap segmentation is claimed.

The runtime ZIP contains Python source/assets, not a bundled Windows executable.
Python dependencies and the existing Plotly CDN are still required.
