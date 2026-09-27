# Multi-element pressure sections — implemented in v25.10

The user approved implementation after reviewing the Excel screenshots on
2026-09-28. This file retains its original proposal filename for existing links.
The user also selected the overall section X extent for combined cl normalization.

## Observed input and supported contract

The screenshots show two consecutive closed geometry contours in one
ABSCISSA/ORDINATE block, with matching pressure rows. The first starts on its
surface, returns to that point, then the second starts. Their X ranges overlap.
The main element includes a rear recess with a vertical constant-X wall; repeated
X is therefore meaningful geometry. Pressure values are absolute Pa despite the
spreadsheet's Cp column heading.

The implementation pairs rows without sorting and detects each return to its
starting X **and** ordinate. Each loop must enclose a nonzero area. Consecutive
duplicate points are allowed and remain paired with pressure. Every element is
explicitly closed; no gap threshold guesses a boundary. The original single
open/blunt contour remains supported when it runs edge-to-edge and back with
monotonic branches. Multiple open contours require explicit exporter connectivity
and are currently rejected.

Elements are named Element 1, Element 2, etc., in source order. Within each loop,
the two ordered paths from its forward X extreme to the first aft X extreme on
each side are labeled using geometry. Their remaining connecting path is
trailing edge / cove. Paths are not sorted by X. Labels refer to the supplied
X-aft/ordinate-up frame, not a reconstructed local LE/TE frame for a deflected
flap. Surface labels do not enter the force integral.

## Forces, normalization and interpolation

For each segment, use the mean endpoint gauge pressure and its outward normal,
with orientation determined from the enclosed signed area. Integrate each loop
independently, then sum its body-frame Fx/Fz. Never integrate a connector between
two elements. Lift per span is `Fx*sin(alpha) - Fz*cos(alpha)`; `cl = L'/(qdin*c)`
and `cl.c = L'/qdin`. Here c is the overall section-file Xmax - Xmin across all
elements, explicitly selected by the user. All elements use that same plotted
x/c, preserving their relative sizes, gaps and overlap.

Matched state geometry allows pointwise pressure interpolation at target ALPHA
or global ADF CLS, including multiple distinct Cp samples at one X. Element
identity/order, geometry and surface correspondence must match between states.
Forces interpolate before projecting at the target ALPHA. Legacy reports without
element records retain their prior separate-surface interpolation path.

Self-crossing loops and touching, intersecting or nested elements are rejected.
Existing positive-q, reference-pressure, constant-flow, beta=0 and planar body
coordinate restrictions remain. Canted/local-normal geometry still needs explicit
section-to-body and span-density mapping. No force-file or viscous shear input
is used.

## Validation and limits

See [v25.10 validation](VALIDATION_v25_10.md). Analytical synthetic tests cover
concave rear recesses, overlapping X ranges, independently reversed/rotated loops,
constant-pressure cancellation, linear pressure-gradient forces, malformed input,
and target interpolation. `generate_multielement_demo.py` generates an isolated
browser example with a deflected flap and dense repeated-X wall samples.

The screenshots establish topology, not exact numeric production validation.
No data was transcribed from rounded image values. Raw exported pressure/section
files are still needed to validate a real CFD case. Automatic local aerodynamic
LE/TE identification, element IDs in multiple blocks and general 3D mappings are
outside this implementation.
