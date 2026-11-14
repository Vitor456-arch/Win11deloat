# Windows validation plan

Use a disposable Windows 11 VM, snapshot before each destructive test, and a non-production local user. Never test removals or privileged changes on the development host. Windows 10 compatibility requires a separate VM. No automatic destructive tests run in CI.

## Read-only smoke

- Install from README and run `python -m pytest -q`. Confirm the Windows integration test actually runs rather than skips.
- Compare OS build, CPU/GPU, memory, current-user packages, startup, services, optional features and tasks against native Windows tools. Check restricted account errors.
- Change themes including Windows system theme. Test 100%, 150% and 200% scaling, keyboard-only navigation, screen reader and contrasting selected rows.
- Scan a known folder with ordinary, empty, inaccessible, hard-linked and junction-linked files. Confirm exact logical sizes, skipped links, cancellation, parent navigation and exports. Test a large drive separately.

## Registry / recovery (test user only)

- Record a preference's original value and type using Registry Editor. Queue it and cancel; confirm no write occurred.
- Apply after explicit confirmation, verify via Registry Editor, restart Explorer/Settings if needed, and check actual UI behavior for this Windows build.
- Restore from Recovery, verify exact original value. Repeat with an originally absent value and confirm absence is restored.
- Modify the value externally after preview: execution must refuse. Modify externally after execution: rollback must refuse to overwrite newer preferences.
- Interrupt the app after a `prepared` event in a debug VM. On relaunch, ensure a new session is blocked, reconcile against actual state, then restore the original value. Copy the SQLite database as needed for recovery analysis.
- Deny Registry access and confirm no success is reported and later actions do not run.

## Restore points

- Inspect System Protection per drive. With protection disabled or normal privileges, requested restore creation must fail clearly and apply no queued changes.
- On an administrator launch with protection enabled, request creation. Verify the unique label and sequence number in Windows before trusting the app's result.
- Trigger Windows creation throttling and ensure missing new points are treated as failure, never success.
- Review failure and success events in history. Reconfirm that restore points are not represented as personal-file or app-data backups.

## Optional app removal

- Install a disposable catalog app for the test user, scan, queue removal, cancel, and verify the app remains.
- Queue again and explicitly authorize; verify the package is absent only for that user, results are logged, and no provisioned/all-user changes occur.
- Test a package update between preview and execution; operation must refuse.
- Verify frameworks, resource packages, non-removable apps, Store, shell and unknown package names cannot enter the execution catalog.
- Reinstall via Microsoft Store if available. Confirm the UI never promises automatic app-data restoration.

## Process termination

- Start a disposable editor with unsaved text; cancel confirmation first, then explicitly terminate and verify exit.
- Attempt a protected process, different-user process, system executable and stale PID/start-time pair. Each must be refused.
- Verify failures are logged and do not turn into success notifications.

## Release gate

Record actual OS builds, permissions, commands, test counts, errors and outcomes. Do not mark the application production-ready until the above Windows behavior has been observed and critical failures fixed. Build artifacts are unsigned unless a real signing workflow has been configured. CI success alone does not validate destructive actions.
