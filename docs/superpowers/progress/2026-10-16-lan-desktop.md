# SDD ledger — plan: docs/superpowers/plans/2026-10-16-beytarchiver-4-lan-prototype.md

Base: f30d92f9b67915d2498aa6383c2bd0f433555655

Ruling: This delivery implements Tasks 1–3 (desktop connection infrastructure),
as explicitly offered immediately before the user's approval. Android / APK
Tasks 4–5 and real-device acceptance Task 6 remain pending, not abandoned.

Ruling: Use the existing isolated `work` checkout; no new worktree or automatic
publication. Cloud-hosted skill scripts have no local executable path, so this
tracked ledger and normal test commands retain the execution record.

Pre-flight: Task 1 session / QR schema is consumed by Task 2 HTTPS and Task 4
Android. Keep v1 JSON fixtures shared. Task 2 event queue is consumed by Task 3;
events contain no credentials. Tk input is captured before starting workers.

Ruling: Polling intervals and certificate identity use explicit deterministic
test clocks / loopback TLS fixtures; production QR validation remains RFC1918-only.

Task 1: complete — 32 protocol / session tests RED→GREEN. Separate pair / poll /
access credentials; local approval; replay, concurrency, expiry and rate limits.

Task 2: complete — actual TLS request / stream tests, file snapshot mutation,
empty / 10 MiB / oversized sources, receipt, cancellation, connection cap,
slow handshake, startup failure and staging cleanup tested.

Task 3: complete — actual Tk navigation and worker-dispatch tests run on DISPLAY=:99;
qrcode==8.2 installed and pinned. Main source / installer version stays 3.7.

Ruling: Add a small `workspace.py` helper alongside the planned files so startup
can recognize process-owned abandoned snapshots safely. It conservatively leaves
unknown files and live process markers in place; abandoned unknown files may
require manual cleanup rather than risking deletion of user data.

Final review: fresh independent reviewer examined Tasks 1–3 and ran 105 tests.
Final: fixed cancelled sender deleting a replacement offer —
test_cancelled_sender_cannot_delete_replacement_offer RED→GREEN.
Final: fixed expiry between HTTP body authentication and receipt commit —
test_receipt_rechecks_session_after_body_read RED→GREEN.
Final: fixed planned orphan cleanup — test_workspace_preserves_active_and_unknown_files_and_cleans_abandoned
and test_workspace_never_follows_symlinks RED→GREEN (implemented while review ran).

Deferred checks, not implementation defects: Android pinning / redirect / SAF
behavior, APK signing and CI generation (Tasks 4–5); actual Windows / phone /
firewall acceptance (Task 6). No public release, push, or 4.0 readiness claim.

Final verification: DISPLAY=:99 python -m pytest -q → 109 passed.
Dependency check: pip check → no broken requirements. git diff --check → clean.
No Android / Windows binary build or physical-device test performed.

## Android delivery — Tasks 4–5 authorized

Toolchain: SDK 35 and Build Tools 34.0.0 installed from official sdkmanager.
Gradle 8.9 distribution SHA-256 and wrapper JAR SHA-256 verified against official
Gradle checksum endpoints. Local build JVM is 21 (Gradle supports it), Java/Kotlin
bytecode target and CI JVM remain 17. No trust / checksum checks disabled.

Task 4 RED: testDebugUnitTest failed on missing client classes; protocol, TLS,
store and repository then passed. ViewModel test failed before ViewModel existed.
Task 4 implementation: QR / pin / same-origin client, streaming staging and SAF
verification, lifecycle cancellation, Compose UI. Real Python interop test added.

Ruling: Resolve annotated Actions v4 tag to its underlying commit before pinning;
gradle/actions tag object is not a commit. Use ed408507eac070d1f99cc633dbcf757c94c7933a.

Task 5: workflow uploads test APK plus SHA256SUMS and reports for 14 days,
contents:read only, no Release publication or permanent signing key.

Independent Android review: one important post-save cancellation/receipt race.
Final: fixed cancel/background after verified save blocking receipt retry —
test_cancellingAfterVerifiedSavePreservesReceiptRetry RED→GREEN; save commit is
synchronized with cancellation, completed file is retained, receipt retry remains
authorized. UI publishes saved status before receipt and disables duplicate retry.

Task 4: testDebugUnitTest + lintDebug + assembleDebug succeeded. 15 JVM tests
include actual Python/OkHttp binary and empty transfers; 109 Python tests passed.
APK v2 signature verified. Lint has 5 warnings (custom pin trust manager, backup
rules, application icon, usable-space check); no lint errors. These polish /
platform annotations remain noted, not hidden as zero-warning verification.
Task 5: actionlint passed after moving runner.temp-dependent SDK env into a step.
A real GitHub run cannot yet be inspected: gh run list HTTP API returns Forbidden.
Local APK creation is verified independently; remote Actions success is not assumed.
