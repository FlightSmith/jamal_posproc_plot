# Screenshot-inspired multi-element synthetic CFD project

This is synthetic validation data, reconstructed from sparse rounded readings
in the supplied Excel photographs. It is not the original export or a CFD solution.

## Open in JAMAL

1. Select this folder as the base directory (it contains 02-RUNS and 03-RESULTS),
   or Load setup from jamal_dashboard_setup.json on the generating computer.
2. Select POLAR-001, POLAR-002 and POLAR-003; use Absolute pressure [Pa].
3. Generate the dashboard and open Distributions. Add overlays and compare at
   ALPHA=3 degrees or global CL=0.3. Centre station Y=0 resembles the screenshots.
4. If this folder is moved, update its path in the setup or select it manually.

## What follows the screenshots

Every paired curve has 603 samples in one block, data on lines 9–611:
main element lines 9–317 (309 points), flap lines 318–611 (294 points).
The main starts at (1.4791, 0.010859) and closes there. Its forward X is1.4742;
aft X is1.9022. The cove wall has X=1.8852, ordinate +0.020040 to -0.020040.
The flap starts/closes at (2.0347, 0.00016610), repeats its first sample,
and reaches forward X=1.8972. Thus the element X ranges overlap.
Repeated X at the nose/TE and the vertical wall are intentional.

screenshot_anchors.json contains the sparse readings. Geometry and baseline
pressure between anchors use shape-preserving cubic interpolation in row number,
not X. Small differences and intermediate rows are invented. Centre-station
POLAR-001/state1 reproduces the transcribed pressure anchors, including the
near-LE maximum and flap feature near X=1.9113. Other states are imposed loads.

## Invented flow and load sweeps

User-selected p=101325 Pa and qdin=0.2*p=20265 Pa; BETA=0 throughout.
MACH=0.534522484, constant Reynolds=6979503.51; BREF=2 m,
CREF=overall section chord=0.5605 m; SREF=BREF*CREF=1.121 m2.
Five stations Y=-1,-0.5,0,0.5,1 m have identical geometry. Loading is multiplied
by 1-0.25*Y^2. Pressure references and all sweep conditions are synthetic.

- POLAR-001: screenshot-like baseline plus Cp increment -1.5*ALPHA*ordinate/chord.
  ALPHAs in file/state order: 0,2,4,6,-2 degrees.
- POLAR-002: the same geometry and baseline, with a stronger flap increment
  (-5*ALPHA-3)*ordinate/chord; main increment as POLAR-001.
  ALPHAs: 0,1,3,5,-2. This supplies a different ALPHA at common CL.
- POLAR-003: analytical Cp = -0.35*(X-Xmin)/chord
  -(1+1.6*ALPHA)*ordinate/chord + constant; constants0.4 main and-0.2 flap,
  before the same span factor. ALPHAs: 0,2,4,6,-2.
- validation_cases/uniform_pressure: different constant Cp on each element,
  so each element and combined Fx/Fz must be zero. Not loaded as a dashboard polar.

State1 is intentionally not the lowest ALPHA, testing original infout order.
Combined cl and x/c use the common all-element chord, as selected by the user.
ADF force/moment data are derived from these pressures, not copied from another
case. Global loads use piecewise-linear trapezoidal integration between stations.
Physical body coordinates are(-X,Y,-ordinate); moments refer to the body origin
(infout XREF=YREF=ZREF=0). No shear, viscous drag or solver convergence is invented.
Missing solver-history/mesh quality warnings are therefore expected; distribution
integrity should have zero warnings. These are not aero performance predictions.

## Independent checks

expected_values.json gives per-element and combined forces, sectional lift/cl,
and global CLS/CDS/CMS for every state/station. Screenshot-like reference forces
use separate two-point Gauss integration. Analytical forces use polygon area:
Fx=qdin*area*dCp/dX and Fz=qdin*area*dCp/dordinate. A constant pressure offset
cancels on each closed element. Forces project using the requested ALPHA.

From the repository root run:

    python -B jamal_dashboard/validate_screenshot_fixture.py

Regenerate from the source generator:

    python -B jamal_dashboard/generate_screenshot_fixture.py --report --zip

The generator only overwrites a folder bearing its SYNTHETIC_FIXTURE.txt marker.
Original fixtures and source JPEGs are never edited. SHA256SUMS.json records the
generated input/reference files; dashboard outputs are excluded.
