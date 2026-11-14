# Development validation

Environment: Linux (Debian 13), Python 3.12, Qt for Python 6.12.0. No Windows machine was available in the development session.

- `python -m pytest -q -ra`: **25 passed, 1 skipped**. The skipped test requires real Windows inventory and metrics.
- Tests include explicit confirmation, write-ahead backups, exact original values and absent-value restoration, changed-value refusal, unexpected Registry types, duplicate/conflicting actions, requested-restore failure gating, optional package protection and missing protection flags, app removal verification, stop-on-error and partial completion, journal reopen, interrupted execution and interrupted recovery.
- Real filesystem tests cover nested size totals, file aggregation, zero-size entries, cancellation, symlink-loop avoidance, proportional treemap rectangles and non-deleting temporary-file preview.
- Headless Qt smoke visits all sixteen sections, switches each theme, runs an asynchronous real directory scan, verifies table results and exercises filtering.
- A real offscreen Storage Analyzer window was captured and visually inspected; screenshot is in `images/storage-linux.png`.
- Python distribution wheel built successfully; `pip check` found no broken requirements.

No actual Windows Registry write, application removal, process termination, restore point, Windows GUI session, packaged Windows executable, or large-drive stress test was executed locally. The in-memory adapter tests validate policy and state transitions, not the correctness of Windows integration. Included GitHub workflows have not been claimed to pass until run results are observed.

Follow `WINDOWS-VALIDATION.md` before using modifications on a non-disposable installation. This is a development foundation, not a production certification.

## Windows release preparation

After the initial development report, release preparation added two packaging
checks (CLI smoke and bundled license/version retention). The local Linux suite
now reports **27 passed, 1 skipped**.

The complete CI matrix passed for commit `6501aee`:
https://github.com/Vitor456-arch/Win11deloat/actions/runs/43621767714

- Ubuntu 24.04 / Python 3.12 and 3.13.
- Windows Server 2022 runner / Python 3.12 and 3.13, including the real read-only
  Windows inventory/metrics integration test and headless Qt UI tests.

Windows CI exposed a real temporary-file-preview bug: Windows `DirEntry.stat`
reports zero for identity/link-count fields, so preview now uses `os.stat` for
those fields. SQLite connections now explicitly close their handles, and smoke
tests shut down the Qt event loop and widgets explicitly.

No destructive Windows changes have been run. Windows 11 interactive, DPI,
accessibility and destructive disposable-VM validation remain outstanding.
The release workflow separately gates publication on portable/installed binary
smoke tests and silent installer/uninstaller checks; consult the release's own
Actions run for their outcome.
