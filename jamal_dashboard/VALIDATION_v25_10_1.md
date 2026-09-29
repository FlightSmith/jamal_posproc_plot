# v25.10.1 performance validation — 2026-09-29

Approved update based on v25.10 / bb3b6fe. The user reports 30–60 minute
generation for 21 states on another computer with network-share inputs. That
dataset is not available here, so its delay and eventual improvement are not
measured. The user approved commit/push; production-computer verification is pending.

## Changes and correctness

Contour validity checks use a conservative hierarchy of segment bounding boxes
before the same tolerance-aware intersection predicate. Nested/touching/crossing
rejection, error precedence, surface point indices, winding and original pressure
quadrature remain unchanged. Five new tests compare candidates with exhaustive
oracles, exercise tolerance boundaries/duplicate points/open contours, and bound
work for finely sampled vertical cove walls. A separate comparison with the
literal approved function matched all 500 randomized contours, including 85
accepted results and 415 exact rejection messages.

Validated topology is cached by SHA-256 of every ordered geometry row, with a
validation version, cached-result checksum and structural validation. Identical
geometry is reused within a generation. Corrupt caches are recomputed; optional
topology-cache write failure preserves valid loads. Pressure and flow results are
not cached, so changes to p, qdin, ALPHA and pressure files are still calculated.
Twelve new cache tests cover these cases, raw source changes during parsing,
unchanged-file metadata reuse, forced rebuilds and file/symlink filtering.

Directory inventory reuses source metadata and resolves a component parent once.
Source fingerprint comparison after changed-file parsing is retained. Short cache
temporary names reduce Windows path-length overhead; short local output paths
remain advisable. Compact JSON only removes formatting whitespace. Its full data
schema and numeric precision remain unchanged.

An optional global output folder places cache and reports locally while reading
the selected network base. Blank retains the old default. Five tests cover default
and explicit paths, output/cache confinement, stage timing logs, and actual
launcher JavaScript setup/draft round trips. Staging permission inheritance and
report publication rollback are unchanged.

## Validation results

`python -B -m unittest discover -s jamal_dashboard -p "test_*.py" -q`

**93 tests passed.** Protected calculations, original fixture hashes, pressure
integration and ALPHA/CL interpolation regressions pass. Both static-margin
definitions retain their negative derivative sign and original normalization.

`python -B jamal_dashboard/validate_screenshot_fixture.py`

**PASS:** 45,225 pressure samples, 75 sections, 21 target comparisons, uniform
pressure cancellation and 104 source-file hashes. This executed 184,346 Python
checks and 193,180 JavaScript checks.

The complete distribution series, source provenance and warnings match the
approved module exactly on the screenshot fixture. Only diagnostic fields are new.

## Local measurements

Python 3.12 on this Windows computer, all source files/cache/reports on local disk.
The screenshot fixture contains three polars, five states each, five stations and
603 points per section. Warm figures below are medians of three runs.

| Operation | Before | After |
| --- | ---: | ---: |
| Distribution reader, forced input parsing | 0.768 s | 0.249 s |
| Distribution reader, unchanged update | 0.613 s | 0.092 s |
| Complete generation, first/forced | 1.527 s | 0.783 s |
| Complete generation, unchanged update | 1.370 s | 0.627 s |
| JSON report size | 22.77 MB | 10.78 MB |

Topology alone: 603 points decreased from 33.9 to 3.07 ms (11x); 1,204 points
from 135.8 to 6.52 ms (21x); 2,406 points from 544.3 to 13.88 ms (39x). Outputs
were identical. Geometry reuse further avoids those checks on unchanged updates.

On the same warm input inventory, repeated source-side `Path.stat` calls dropped
from 462 to nine, and `Path.resolve` from 180 to three. File information now comes
from directory entries. These counts describe Python calls, not measured SMB
requests; the production network saving remains unmeasured.

A separate generated workload has **21 states, nine stations and 2,406 points per
section**. All **454,734 Cp samples** and pressure-gradient analytical forces were
verified. Complete local generation took **6.75 s**, then **5.80 s** for an
unchanged update. The reports total about 221 MB; writing/validating them now
dominates this synthetic workload. Shared geometry in the report is a possible
future optimization; this update preserves the existing report schema.

Reproduction scripts and detailed timing JSON live in ignored
`DASHBOARD/perf_20260929/`. The stress fixture is separately generated under
`DASHBOARD/s21_9fac15/`; no supplied fixture or screenshot was modified.

## Production check

Use the essential-file ZIP on the other computer, choose a short local output
directory for the network CFD base, and run Generate / Update twice with Force
full rebuild unchecked. Keep the generation log: it records phase timings,
distribution substeps, geometry cache reuse, and actual output/cache paths.
The first generation reads inputs; subsequent updates reuse unchanged files.
Real production timing, raw production geometry verification and network-share
ACL confirmation remain pending. Portable/offline deployment remains separate.

## Essential-file package

`JAMAL_Dashboard_v25.10.1_Real_Environment.zip` contains ten files (99,296 bytes):
three Python modules, four runtime HTML/JavaScript assets, pinned requirements,
START_DASHBOARD.cmd, and package-specific quick-start instructions. The launcher
uses normal installed Python or a local virtual environment. Previous approved
ZIPs were left unchanged. Archive integrity, extracted launcher help and complete
generation from the extracted application all passed, with 15 source series,
603 points per section and no distribution integrity warnings.

SHA-256: `ccfbc9a44ff40b7ef0f619be3d2598a8ee30fb106222bd4ad4f16e2cc7589d7d`.
