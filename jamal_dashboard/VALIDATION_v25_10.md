# v25.10 multi-element validation — 2026-09-28

Approved release based on v25.9 (6ceb551). User authorized multi-element support,
the screenshot-inspired dataset, commit/push, and the runtime package. The existing
overall section chord was explicitly selected.

## Automated checks

`python -B -m unittest discover -s jamal_dashboard -p "test_*.py" -v`

**71 tests pass.** The original 55 regressions remain, with the obsolete rejection
of every closed extra-X turn replaced by rejection of a genuinely crossing
contour. Sixteen new tests cover backend geometry/forces, target interpolation,
and plotting helpers. Existing fixture checksums and protected-source AST checks
pass, including both static-margin definitions and inherited staging permissions.

The multi-element analytical oracle uses `Cp = a*X + b*ordinate + constant`:
body `Fx = q*a*sum(area)` and `Fz = q*b*sum(area)`. It verifies separate element
integrals, combined lift projection and chord normalization. Independent constant
pressure levels on three elements produce zero load, exposing artificial bridges.
Other cases include a concave recess, vertical repeated X, duplicate coordinates,
arbitrary start points, independent winding, missing closure, crossing/overlapping
solids, and pressure/geometry mismatches. An additional review sweep checked 144
combinations of starts and traversal directions against the analytical forces.

End-to-end tests parse synthetic pressure/section files, load them with infout
references and run the JavaScript ALPHA/CLS interpolation on that output. Tests
check preservation of every surface, element identity, repeated-X samples, target
lift rotation, absent-load guards, and rejection of changed topology/geometry.
UI tests check separate geometry/pressure traces, shared style/legend, escaped
hover labels, and common dimensional/normalized/reversed coordinates.

## Browser verification

Generated `DASHBOARD/multielement_demo/CFD/03-RESULTS/DASHBOARD/dashboard.html`
using `generate_multielement_demo.py`. The demo includes two POLARs, nine stations
and five states per polar, with a rear recess and aligned/deflected aft elements.

- Initial report: zero distribution integrity warnings.
- At ALPHA=2.5, both polars interpolate between states 2/3 with different weights.
- At global CLS=0.5, each polar finds its own ALPHA and interpolation weight.
- Each overlaid station renders ten Cp paths (five per source), four independent
  element outlines and two source legends. No inter-element connector is drawn.
- Expanded center-station view visually preserves the recess, gaps, overlapping
  X ranges, flap deflection and equal geometry scaling.
- Shared manual Cp limits display the same inverted -2..1 ticks; both polars
  retain the common source styling. No browser warning/error logs were reported.

## Screenshot-inspired fixture

The separate `JAMAL_SYNTHETIC_MULTIELEMENT_SCREENSHOTS` project reconstructs the
603-row topology from sparse image readings. User-selected p=101325 Pa and
qdin=20265 Pa accompany three polars, five states each and five stations.
`validate_screenshot_fixture.py` passes all 45,225 pressure samples, 75 sections,
21 recorded/interpolated ALPHA/CL targets, analytical forces, uniform-pressure
cancellation, and 104 source-file hashes. Its global ADF loads derive from its
own pressures. Browser checks confirm the centre-section shape and all three
polars comparing at global CL=0.3 with zero distribution integrity warnings.

## Remaining external validation

The user-provided JPEGs were read as topology guidance and left unchanged; exact
production Cp/load validation needs raw paired pressure and section files.
The synthetic demo's global ADF polars are copied comparison inputs, not a span
integral of its invented pressure field. Real network-share ACL confirmation is
still pending. Local/canted geometry retains the existing unavailable-load guard.
Python dependencies and Plotly are not bundled; portable/offline work is deferred.
