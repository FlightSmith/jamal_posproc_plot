# v25.11 launcher validation — 2026-09-30

User-authorized implementation, commit and push, based on v25.10.1 / 1ca634d.
The user reports that moving Python execution onto the Linux data server resolved
the major file-access delay. The production Linux environment is unavailable here;
the checks below used this Windows computer with Python 3.12 and Node.js.

## Behavior

- Removed the output-folder setting. Generation and cache clearing use the first
  configuration's `03-RESULTS/DASHBOARD`; legacy overrides are ignored.
- Accept up to five positional NAME PATH pairs, a single PATH with name Baseline,
  or no pairs for Baseline at the launching current directory. Relative paths use
  that directory. Standard host/port/no-browser switches can be intermixed.
  Argument parsing neither scans CFD data nor imports Tk.
- Command-line values populate the page and begin shallow discovery. A new process
  overrides a stale draft; same-process refresh retains edits. Saved setups still
  work. Windows CMD passes arguments and preserves the caller's directory.
- Three global loading options default on: distributions, convergence and drag
  rise. They persist in setups/drafts and suppress optional source discovery and
  reads when off. Drag-rise discovery is also skipped during Scan when unchecked.
- Infout remains available for reference geometry, deflections, flow and cases.
  Convergence-off mode never discovers or reads a Fluent log/transcript. Separate
  cache entries keep enabled histories from appearing in disabled reports and
  allow re-enabling without losing the existing cache. Changed inputs are checked.
- Reports identify skipped modules; omitted Fluent files are absent from
  provenance. Missing reference data is still reported honestly.

## Automated verification

`python -B -m unittest discover -s jamal_dashboard -p "test_*.py" -q`

**112 tests passed.** New checks include all eight optional-loading combinations,
fresh/warm/forced generation, and guards that fail if disabled sources are opened,
stat'ed or enumerated. Re-enabling after changes to Cp, Fluent and drag-rise files
loads the new values. ADF rows, static margins and infout reference values match
the all-enabled results. Retired output overrides cannot redirect generation or
cache clearing; source data, other caches and existing reports are preserved.

CLI checks cover paths/names with spaces, relative paths, working-directory
defaults, malformed pairs, duplicate labels, maximum configurations and headless
startup. Tests execute the actual launcher JavaScript for startup precedence,
refresh persistence, setup round trips, outgoing loading flags and drag controls.
Deferred-response tests verify that changing drag loading during a pending scan
preserves selections and that stale scan responses/errors cannot replace newer data.
Generated JavaScript syntax and protected aerodynamic calculations remain covered.

`python -B jamal_dashboard/validate_screenshot_fixture.py`

**PASS:** 45,225 Cp samples, 75 sections, 21 ALPHA/CL target comparisons, uniform
pressure cancellation and 104 source hashes. This includes 184,346 Python and
193,180 JavaScript checks. Original source fixtures and user screenshots were not
changed. Both static-margin definitions, pressure integration/projection,
performance caches and staging permission inheritance/rollback are preserved.

## Live launcher check

Started the actual launcher with `--no-browser`, a temporary localhost port and
two named configuration paths. In the browser, both CLI labels and full paths
appeared automatically, their POLARs were discovered, all three loading controls
were checked, and the output-folder selector was absent. The page showed the
first base's output/cache paths read-only. The temporary tab/server were closed.

Production Linux execution and actual network-share ACL verification remain
external checks; no new installation, portability or offline behavior is claimed.

## Essential runtime package

`JAMAL_Dashboard_v25.11_Real_Environment.zip` contains ten essential runtime files
(102,119 bytes) with Linux and Windows quick-start instructions. Previous packages
were preserved. Archive integrity and generation from the extracted package passed
with optional sources on, off and on again. An actual packaged launcher process
started from a different working directory with no configuration arguments; its
HTTP startup state correctly used that current directory with label Baseline.
The temporary process was terminated after the check. No Tk interaction occurred.

SHA-256: `6a1a9adea28835083d5715de66d1c740a0492b1b9c8145e7a6a7230561ccb299`.
