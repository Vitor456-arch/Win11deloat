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
