# Capability status — 0.1.0

Do not equate the presence of sixteen navigation sections with full implementation of the product brief.

| Capability | Implementation | Validation boundary |
| --- | --- | --- |
| Native desktop UI, 16 sections, light/dark/system themes | Implemented | Headless Qt navigation, themes and asynchronous real scan tested on Linux and Windows CI; real Windows DPI/accessibility review pending |
| Windows hardware, Appx, startup, services, tasks, features | Implemented, read-only | Windows read-only integration passed on Windows Server 2022 CI / Python 3.12 and 3.13; Windows 11 interactive validation pending |
| Fresh Windows / presets | Reviewed installed package matches; presets filter only | Catalog/policy tested with injected adapter; real Windows VM validation pending |
| Optional app removal | Exact current-user package, verification, explicit queue approval | Policy tested; real removals intentionally unrun |
| Registry preferences | Four reviewed per-user preferences | Original-value/absence backups, rollback, external-change refusal and partial execution tested with injected adapter; actual build-specific behavior unrun |
| Restore points | Native inspection, explicit creation, unique-label verification, failure stops queue | Safety gate tested with injected adapter; actual System Protection/privileged creation unrun |
| Queue/history/recovery | Durable prepared events, per-action results, interruption reconciliation, original-value restoration | Automated tests cover failures, interruption and journal reopen; full power-loss testing pending |
| Processes/memory | Real readings, sampled CPU, recent samples, confirmed user-process termination | Adapter implemented; actual Windows measurements and termination need VM validation |
| Before/after | Manual timestamped samples, deltas | Not guaranteed idle; no causal performance gains claimed; no boot measurement |
| Storage | Iterative scan, cancellation, proportional treemap, navigation, search, numeric sorting, JSON report | Real fixture files and asynchronous Qt scan tested; million-file and all-volume stress tests pending |
| Cleanup | Old current-user temp preview, opens native Storage Sense | Preview tested; direct deletion intentionally disabled until race-resistant handle-based implementation exists |
| Startup | Inventory and native Settings management | In-app mutation/reversal not implemented |
| General apps/uninstall | Inventory and native Settings management | Arbitrary uninstall invocation / leftover cleanup not implemented |
| Services | Inventory only; no necessity inferred | Dependencies, criticality analysis, configuration and recovery not implemented |
| Privacy/personalization | Advertising, suggestions, file extensions; native Settings links | Broad permission controls / telemetry policies not implemented |
| Gaming | Game Mode preference, monitoring, native Settings link | FPS, power plans, overlays and automatic gaming profiles not implemented |
| Health | OS/CPU/GPU/feature/task inventory | Temperature, GPU usage, SMART, repairs, detailed disk activity not implemented |
| Packaging | Source install; Inno Setup and portable ZIP release workflow with package smoke tests and hashes | Unsigned development preview; see release Actions for package test outcomes |

## Next implementation priorities

1. Execute the disposable Windows VM validation matrix and fix observed integration issues.
2. Validate keyboard, screen-reader, high-contrast, DPI and small-screen behavior on Windows.
3. Add a narrow, reviewed current-user startup adapter with full backup and security-product protection.
4. Add handle-based race-resistant Recycle Bin/file operations and cleanup result accounting.
5. Add measured process owner/signature/disk I/O, optional feature dependencies and extended recovery tests.
6. Stress-test large drives and introduce paging/SQLite indexing where needed.
7. Produce signed builds only after release checks and dependency/license review.
