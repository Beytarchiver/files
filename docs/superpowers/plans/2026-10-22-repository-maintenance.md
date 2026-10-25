# Beytarchiver repository maintenance

**Goal:** Repair broken imports, separate application code from tests and drafts, make the Flet application work with installed Flet 1.0.5, and validate the existing desktop/LAN behavior.

**Architecture:** Keep the desktop entry point and Kotlin Android project in place. Restore the established `lan_transfer` package and `tests/lan` layout. Put the Flet entry point in `mobile/main.py`; preserve the alternate desktop source under `drafts/`. Share UI-independent archive helpers through `beyt_core.py`.

**Scope:** User requested folder organization and code repairs. Preserve existing source contents when moving files, existing design documents, `docs/status.json`, virtual environment and release outputs. Do not publish or run the maintenance-mode script.

- [x] Reproduce current import/test failures, record baseline status.
- [x] Restore LAN package and test locations, move mobile and desktop draft sources to dedicated directories. Verify imports and test collection.
- [x] Add archive and Flet smoke regression tests. Implement the missing core using the existing desktop extraction logic, including cancellation/progress and safe ZIP validation.
- [x] Update Flet 1.0 API calls and job ownership; test picker flows, repeated job starts, cancellation, wrong passwords and preservation of existing outputs.
- [x] Repair Windows build root handling; document dependencies, layout and run/test/build commands. Ignore generated caches.
- [x] Run Python regression suite, UI construction/picker smoke tests, PowerShell syntax/path checks and inspect final diff. Report Android SDK/JDK or packaging limitations accurately.

## Initial evidence

- Desktop import fails with `ModuleNotFoundError: lan_transfer.panel`.
- LAN sources and tests are mixed in untracked `lan/`; tracked original paths are deleted.
- Flet sources import missing `beyt_core`; `ft.ElevatedButton` is absent in Flet 1.0.5.
- Windows build script uses uninitialized `$RepoRoot` to find its root.
- Project virtual environment initially lacks pytest, Pillow and qrcode.
- Host Java is JRE 8 and default Android SDK location is absent; APK build requires a separate configured JDK 17 / SDK 35 environment.

## Execution notes

Work proceeds inline under the user's authorization. File moves are confined to the repository and refuse existing targets. No commits or publication are required. Verification commands and final results are recorded in the maintenance report.

## Verification results

- Full Python suite: 130 passed, 10 skipped in 42.03s; unhandled worker exceptions promoted to errors.
- Skips: 4 symbolic-link capability tests, 1 hard-link capability test, 5 Tk display tests.
- Flet archive and UI suite: 23 tests passed, included in full suite.
- All 23 Python source files parsed; desktop, LAN and mobile imports passed.
- Flet entry point tested from outside repository with ft.run intercepted; no native window opened.
- pip check: no broken requirements.
- PowerShell syntax and build_windows.ps1 -Check passed from outside repository; caller location preserved.
- Git diff whitespace check passed. Existing status.json edits preserved.
- Independent review identified terminal progress ordering and completed-snapshot cleanup races; both corrected, with regression tests.
- Old cache-only directories lan/ and lan_transfer/beytarchiver_mobile/ remain: automatic permission review rejected both recursive cleanup and the narrower file-by-file cleanup because sandbox approval is disabled.
- No APK/EXE/installer compilation, publication or real-device GUI validation claimed.
