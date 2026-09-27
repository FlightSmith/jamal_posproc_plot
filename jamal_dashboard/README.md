# JAMAL Aerodynamic Results Dashboard v25.10

Approved release. For runtime installation, see [QUICK_START.txt](QUICK_START.txt)
and [requirements.txt](requirements.txt). The runtime ZIP is generated in the
repository root and includes a release commit/file manifest. Python and internet
access for Plotly remain required; this release retains the Python/browser launcher.

## Multi-element sections (v25.10)

Consecutive closed contours in one section/pressure curve are now supported.
Each element must return to its starting **X and ordinate** before the next
element begins. Pressure rows must follow the matching geometry rows. Elements
are numbered in file order; X overlap, arbitrary starting points, reversed
traversal, repeated X, and duplicate consecutive points are supported.

Upper/lower paths and the connecting trailing-edge/cove path are plotted
separately, preserving vertical walls and recesses. All use the source's existing
style; hover identifies the element and surface. Geometry outlines are also
separate, so no line joins one element to another. Surface names describe the
geometry relative to X aft / ordinate up; they do not infer a deflected element's
local aerodynamic chord direction.

Pressure forces are integrated on each complete contour, summed, then projected
to lift at ALPHA. As selected by the user, **combined cl and plotted x/c retain
the overall section chord, Xmax − Xmin across all elements**. Target ALPHA/CL
interpolation preserves matched point order within each element, including coves
and multiple Cp values at the same X. Changing element topology/geometry is rejected.

Open multi-element contours, self-crossings, touching/intersecting solids, and
nested contours need corrected geometry or explicit connectivity; they do not
produce loads. The original open/blunt single-element format remains supported.
No element is identified by pressure magnitude or a jump in X alone.

The supplied Excel screenshots guided the topology. They were not transcribed as
production data. An isolated reproducible demo is available by running
`python jamal_dashboard/generate_multielement_demo.py` from the repository root.
It writes to `jamal_dashboard/DASHBOARD/multielement_demo/` and leaves the original
fixtures and screenshots untouched. POLAR-002 demonstrates a deflected flap.
Its copied global ADF polars are for target-comparison demonstration, not an
integral of the invented pressure field. See [validation](VALIDATION_v25_10.md).

A more detailed, standalone screenshot reconstruction is now available in
`JAMAL_SYNTHETIC_MULTIELEMENT_SCREENSHOTS/` (separate from the original fixtures).
It preserves 603 ordered samples per station, the observed coordinate/pressure
anchors, the cove and repeated flap start. User-selected references are
`p=101325 Pa` and `qdin=0.2*p=20265 Pa`. Three polars and five stations provide
screenshot-like sweeps, analytical pressure-gradient forces and a uniform-pressure
zero-load check. Unlike the earlier visual demo, its global ADF loads are derived
from its own pressure fields. See that folder's README, `expected_values.json`
and `validation_results.json`. Reproduce with `generate_screenshot_fixture.py`
and check using `validate_screenshot_fixture.py`; a ready-to-load ZIP is alongside
the folder. This remains approximate synthetic data, not the original CFD export.

## Pressure distributions and target comparisons (v25.9)

The v25.9 update implemented the requested distribution items 1–6. The current
approved version adds item 7. Portable Windows packaging and offline Plotly remain
separate future work; this launcher still uses Python and a browser.

In each launcher configuration, choose **Distribution file values**:

- **Absolute pressure [Pa]** (default): Cp = (p_local − p) / qdin using infout
  `p[Pa]` and `qdin[Pa]` (not `ptot` or `qimp`).
- **Legacy Cp**: for existing already-normalized files, including the unchanged
  original synthetic dataset. Old setups without a format field default to pressure;
  select Legacy Cp explicitly when reopening old Cp data.

`total_force_state*` files are ignored. Pressure and section files must contain
the same samples in the same contour order, as confirmed for the new export.
Closed contours may start at any surface point. The matched geometry identifies
upper/lower; pressure magnitude does not. Both
surfaces retain the same color/dash and one legend entry; hover names the surface.

The pressure force is integrated around the closed section contour, including
its axial component, then projected to lift at ALPHA. `cl = L'/(qdin*chord)` and
`cl.c = cl*chord`. Loads are pressure-only and exclude viscous shear. Supported
load geometry uses X positive aft and ordinate positive up, with BETA=0 and
constant flow matching the infout reference. Local/canted section coordinates
need an explicit body-axis and span mapping. In particular the original synthetic
VTAIL retains Cp but now reports pressure-derived lift unavailable. Invalid or
ambiguous contours retain recorded Cp where possible and explain missing loads.

To compare different polars or configurations:

1. Select each source and use **Add overlay** to retain it.
2. Set **Compare at** to **Specified ALPHA** or **Specified CL (Stability CLS)**.
3. Enter a target and leave the field. Every selected source is reconstructed at
   that target using its own sweep. CL is the global ADF CLS, not sectional cl.

CL matching first inverts each piecewise-linear CLS/ALPHA sweep. Pressure surfaces
are then interpolated separately between bounding states; forces interpolate at
fixed geometry, and lift is projected at the target ALPHA. Source states and
weights are shown and included in the text export. Extrapolation, multiple CL
crossings, changing geometry/flow, and missing or ambiguous station matches are
rejected with an explanation. Recorded-state viewing remains available.

**Cp scale → Specify limits** applies minimum/maximum to all visible station plots
and their expanded views. Automatic scaling remains the default. Limits stay
inverted so negative Cp is upward; invalid limits display an explanation and use
automatic scaling. Target/scale selections are remembered with the distribution view.

Residual plots versus ALPHA/BETA now start at 1e0 and extend down to 1e-9.
Existing iteration-history scales and protected scientific calculations are unchanged.

Keep the new `distribution_interpolation.js` beside the existing Python, HTML,
and JavaScript assets; it is embedded when reports are generated. Current suite:
**71 passing tests**. See [v25.10 validation](VALIDATION_v25_10.md) and the
[multi-element design and input contract](MULTIELEMENT_PROPOSAL.md).

## Earlier updates

New in v25.8: Cp station cards include Expand, preserving the section outline and
transparent hover labels. Distribution headings show only Re/Mach. Drag-rise
Re/Mach appears once above all targets. Delta shows the sweep's constant angle,
with Xref between the force and moment rows.

Static margin now offers Longitudinal (-100 dCMS/dCLS, % CREF) or Directional
(-100 dCNS/dCYS, % BREF), both in Stability axes using the active moment reference.
Select synthetic POLAR-003 to check the directional option: alpha is fixed at 3°,
beta sweeps from -8° to +8°, and the signed result is +15% BREF at the original
reference. Three finite distinct CY values and constant alpha are required.
See JAMAL_SYNTHETIC_CFD/README_DIRECTIONAL.md for formulas and reproduction.
The Delta tab's optional static-margin comparison remains longitudinal.

New in v25.7: Convergence shows each residual equation in a three-column grid
against ALPHA or BETA, with cp-max and tstep-ave below on independent axes.
Additional turbulence equations are discovered from Fluent headers. Delta shows
all six coefficient comparisons and collapsible additional plots. In the launcher,
Ctrl-click multiple drag-rise folders to overlay configurations at each filename
CL target; targets appear in rows of three. Existing single-folder setups still work.
Spanwise cl and cl.c now have Expand, PNG and SVG actions. Analysis plots show
Reynolds/Mach; Xref is shown where moment references apply.
All axis titles are bold and 10% larger. Cp layout and hover behavior are preserved.
Keep `dashboard_panels.js` beside the Python engine and distribution assets when
copying the application; it is embedded into generated standalone reports.

Network-share patch: report staging folders now use normal directory creation
to inherit the destination folder's Windows permissions, instead of tempfile's
restrictive ACL request. Report validation and rollback remain enabled. Existing
folder permissions are not modified. Validation on the affected share is pending.

ADF files are sufficient to load the dashboard. Run histories, load/Cp distributions
and drag-rise inputs are optional. When FLUENT_LOG is absent, the newest `.trn`
file by modification time is used. If no history is available, coefficients remain
accessible and convergence is reported as unavailable. Reference shifts require
infout geometry; without it, original ADF moments are displayed. Adding/removing
logs or changing the selected transcript automatically invalidates the polar cache.

Approved plot-first layout: summary and reference details are collapsible, coefficient
conditions and curve visibility controls are shared, and L/D opens under Additional
plots. Expand, PNG and SVG actions are available beside analysis plots. The existing
Cp and spanwise distribution interface is preserved. The pre-layout checkpoint
is commit 696c0fd. Selected residual, aero and cp-max/time-step histories share
one row. Redundant convergence coefficient-versus-alpha panels are removed.
Coefficient conditions show fixed BETA for ALPHA sweeps, or fixed ALPHA for
BETA sweeps; differing conditions are identified by configuration and polar.

Coefficients shows three force plots in a row, then three moment plots below,
followed by L/D. Choose Body, Stability or Wind axes, then ALPHA, BETA,
selected-axis CL or CY as the horizontal coordinate. Self-plots are omitted.
Headings show Reynolds and Mach, plus Xref for moments. The moment reference
applies to all moment plots, and L/D uses CL/CD from the chosen axes.
Delta also provides independent axis and coordinate selectors. Drag rise supports
all three axes using their source drag columns and a lowest-Mach baseline;
file groups retain their original CLS targets. Missing axis data is reported.
These controls are retained in saved views and presets. Numeric ticks and values
use the original Arial font; word headings retain their existing typography.
Drag-rise titles show the selected-axis lift coefficient and its actual range.
Spanwise cl/cl.c and static margin use two columns; residuals, drag rise and
Delta use three columns,
stacking on screens below 760 px. The Cp station layout is unchanged.

Each Cp station panel includes its section outline underneath, using a shared
x/c axis and an independent y/c axis with equal geometric scaling. The ordinate
comes directly from the section file divided by local chord (no sign change,
rotation or recentering). Xmin/Xmax selection applies to both Cp and geometry;
dimensional-X mode uses metres. Matching colors, dashes and legend toggles link
the pressure curve and outline. Section geometry comes from section_state1.

Cp hover labels use transparent backgrounds and curve-colored text to keep small
station plots readable. Local Git workflow instructions are in ../GIT_WORKFLOW.md;
the v25.3 tag preserves the version before this hover styling change.

## New in v25.3

All span coordinates use infout BREF, including VTAIL. The span-coordinate selector
also controls Cp station labels: 2Y/BREF and Y/BREF appear as percentages; Y [m]
appears in metres. Component span metadata remains geometry provenance only.

Separate spanwise plots show cl and cl.c (cl times local chord, in metres).
Legends display alpha and beta. Save spanwise loads (.txt) exports every station
of the displayed states and pinned overlays, with both loads, chord, BREF and
coordinate metadata. Missing values are marked NA; Cp station selection does
not limit the load export.

Cp uses a responsive grid of separate station plots with common inverted limits.
Selections are retained when switching coordinate modes. Different components
remain in separate panels. All stations are selected initially.

The synthetic dataset now includes a paired **VTAIL with a 5 m projected span and
45 degree cant**, alongside the original 10 m wing. See
`JAMAL_SYNTHETIC_CFD/README_VTAIL.md` for geometry, force-density conventions and
expected values. The original source fixtures are unchanged. Production V-tail
physics remains unvalidated; the new data is an illustrative test fixture.

Historical v25.3 development suite: **26 passing tests**, including numerical tail values,
span-reference changes, normalized station grouping and original protected modules.

This package contains a lightweight local launcher and the standalone dashboard engine.
No Flask, Dash, or web framework is required.

## Files

- `jamal_dashboard_launcher_v25.py` — local browser launcher, shallow folder discovery, incremental cache, live progress, setup save/load.
- `jamal_polar_convergence_dashboard_v25.py` — validated standalone dashboard engine.

Keep the two scripts and these new assets in the same folder:

- `jamal_distributions.py` — separate DISTCLCP parser, station matching, raw-file cache and integrity checks.
- `distributions.html` and `distributions.js` — embedded Distributions tab; no separate files are needed beside a generated report.

Script filenames remain `*_v25.py` for launcher compatibility. Version v25.10 is
reported inside the application. The untouched original scripts and README are
preserved in `baselines/v25`.

## New in v25.1

- **Distributions:** sectional cl and inverted-axis Cp plots; state, POLAR,
  component and configuration selection; overlays; station selection, every-nth
  selection and single-station mode; remembered selections per source project.
- Separate incremental geometry/force/Cp caches. Only selected POLARs are inspected
  during generation. Original shallow discovery remains unchanged.
- Station matching within 1e-6 m, original Cp surface order, dynamic component
  names, source provenance and explicit integrity warnings.
- Exponent-aware reference coordinates and qdin parsing. Duplicate configuration
  labels and overlapping generation/cache-clear operations are rejected.
- Reports are staged and validated before publication, with rollback if ordinary
  file replacement fails. Progress monitoring retries transient errors and can
  reconnect to active jobs after a page reload.
- Existing initialized plots use Plotly.react for updates and retain zoom when
  axis definitions remain the same. New distribution plots render when their tab opens.

The moment-transfer equations, static-margin derivative, Fluent subblock parser,
drag-rise definition, Delta interpolation, and residual thresholds remain unchanged.

## Distributions conventions

Inputs: `03-RESULTS/DISTCLCP/POLAR-XXX/<component>/` containing
`section_state1_station*` and `cp_dist_stateS_station*`. `total_force_stateS` is
ignored. Pressure defaults to absolute Pa; explicitly select Legacy Cp for older
normalized inputs. States follow the original infout case order. Integrated
pressure force is per unit span, using the coordinate convention described above;
cl uses `L'/(qdin*chord)` with no delta-Y factor.

The module has been checked against synthetic data. Production validation is
pending. Missing pressure references or changing flow prevent normalization;
nonzero beta or unresolved coordinate mappings omit lift with an explanation.
Recorded Cp remains available where normalization and geometry permit.

The default Cp normalization assumes Xmin is the leading edge, as explicitly
confirmed by the synthetic fixture. For other geometry, select Xmax or dimensional
X for display. This selector does not change the force coordinate convention.
Upper/lower surfaces are separated before interpolation; their samples are never
mixed by global X sorting. All normalized span coordinates use infout BREF.

## Validation

```bash
python -m unittest discover -s jamal_dashboard -p "test_*.py" -v
```

Run from the parent folder; from inside `jamal_dashboard`, use `-s .` instead.
Tests require NumPy, pandas and Node.js, and use disposable copies of
`JAMAL_SYNTHETIC_CFD`. They cover numerical fixture values, cache reuse, failure
handling and unchanged protected source functions. See `VALIDATION_v25_10.md`.

The launcher is intended to run as a single process per output project. Its job
lock does not coordinate separate launcher processes. Staged publication handles
ordinary writer failures, but two filesystem paths are not a crash-atomic
transaction and external readers are not covered by the HTTP read lock.

## Run

```bash
python jamal_dashboard_launcher_v25.py
```

The launcher opens in your default browser. If the browser does not open, use the local URL printed in the terminal.

## Expected JAMAL structure

```text
<BASE>/
├── 00-SUPPORT/
├── 01-GRIDS/
├── 02-RUNS/
│   └── POLAR-XXX/
│       ├── infout
│       └── FLUENT_LOG
└── 03-RESULTS/
    ├── ADF/
    │   ├── POLAR-XXX.adf
    │   └── ADF_COMP/        # ignored during discovery
    ├── DRAG-RISE/
    │   └── <optional folders>/
    └── DASHBOARD/           # created automatically
        ├── dashboard.html
        ├── dashboard.json
        └── .jamal_cache/
```

## Two-phase workflow

### Phase 1 — Fast discovery

For each configuration, select the JAMAL base directory. The launcher performs only:

- one shallow listing of `03-RESULTS/ADF`;
- one shallow listing of `03-RESULTS/DRAG-RISE`.

It does not recurse into `ADF_COMP` and does not inspect `02-RUNS` during discovery.

### Phase 2 — Generate / Update dashboard

Only selected POLARs are inspected. The launcher fingerprints the selected:

- `POLAR-XXX.adf`;
- `infout`;
- `FLUENT_LOG`.

The fingerprint uses source path, file size, and modification time.

- New POLAR: parsed and cached.
- Modified POLAR: reprocessed and cache replaced.
- Unchanged POLAR: reused from cache.
- Unchecked POLAR: omitted from the new dashboard but may remain cached for later reuse.

The standalone HTML and JSON are regenerated from the complete current selection, which is inexpensive compared with parsing large Fluent logs.

## Generation status

The top panel shows:

- generation phase;
- percentage progress;
- new, modified, cached, and forced-rebuild counts;
- current configuration/POLAR;
- parsing log;
- final parsed/reused counts and elapsed time.

## Cache controls

- **Generate / Update dashboard** — parse only new or modified sources.
- **Force full rebuild** — ignore cache for the current run.
- **Clear cache** — remove `03-RESULTS/DASHBOARD/.jamal_cache`; generated dashboard files are kept.

## Outputs

The first configuration is the output project. Files are written to:

```text
<first configuration>/03-RESULTS/DASHBOARD/dashboard.html
<first configuration>/03-RESULTS/DASHBOARD/dashboard.json
```

Automatic `convergence_comparison.csv` and static-margin CSV files are no longer generated. CSV exports remain available explicitly inside the standalone dashboard.

## Setup files

**Save setup** stores configuration labels, base directories, selected POLARs, and drag-rise directory selections in a small JSON file. It does not store CFD results.

**Load setup** restores those selections and performs fast discovery for the configured base folders.

## Dependencies

The dashboard engine uses:

- Python 3.9+
- NumPy
- pandas

Plotly is loaded by the generated standalone HTML from the configured CDN reference, as in previous versions.
