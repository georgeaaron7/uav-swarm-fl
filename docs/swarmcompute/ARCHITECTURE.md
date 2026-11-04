# Architecture

One Python/FastAPI/Uvicorn coordinator serves both `/api/v1` and the compiled React application. It uses SQLAlchemy Core with Alembic migrations and SQLite WAL on local disk. No Redis, Ray, Celery, Kubernetes, paid infrastructure or Node runtime service is required. Workers poll over outbound authenticated HTTP; each physical laptop executes a complete simulation, whose UAV clients remain virtual.

`swarmcompute/coordinator/scheduler.py` is the scheduler/executor boundary. Immediate SQLite transactions serialize claims, lease renewal, retries and terminal publication. Studies/jobs/attempts, users/enrollment/worker credentials, events, settings and artifact references persist in the database. An active attempt has a unique random fencing token and generation. Every mutating attempt endpoint checks worker ownership, current attempt, live lease and token. A stale attempt cannot upload or complete a replacement result.

`run_context_study.build_jobs()` remains the only configuration generator. Stable IDs hash canonical scientific configuration, study ID, data/trace fingerprints and scientific source hash; machine paths, device and thread count are excluded. `completed()` remains part of final validation. Source hashing is lazy and Torch is not imported by the coordinator. Optional `server`, `worker` and `dev` dependencies are separate.

Workers use NVML/psutil sensors, explicit resource admission, a heartbeat thread independent of uploads, and an isolated `python -m run_baseline` process. Structured round progress is written atomically to a local JSON file. Stop requests and lease deadlines are observed at completed-round boundaries. Worker-local artifacts are caches; central validated artifacts are authoritative. Logs are bounded to the most recent 64 KiB per attempt. Unavailable sensor fields are null.

The database-backed scheduler considers only running studies, healthy/unpaused workers with approved source/data, resource/battery/temperature eligibility and configured cluster concurrency. It prioritizes resumable jobs then FIFO creation order. One active process per worker is enforced. GPU multi-process capacity is not guessed from model names. Scientific paired seeds and data partitions are unchanged; source/runtime provenance records environment differences rather than claiming equivalent GPUs.

Results/checkpoints use attempt-scoped resumable chunk uploads, SHA-256, exact archive-member allowlists, expanded-size limits and immutable content-addressed files. Authoritative references are committed inside a database transaction. Physical execution is at-least-once; terminal publication is idempotent and exactly one logical result is authoritative. Worker crashes and coordinator restarts reconcile persistent leases; no in-memory queue is authoritative.

Browser sessions use expiring bearer tokens, explicitly set in Authorization headers. Cookies are not accepted for authentication and cross-origin requests receive no CORS permission; browser-authenticated mutations therefore cannot be triggered with a cross-site cookie/form (CSRF). Passwords use Argon2. Enrollment codes/session/worker tokens are stored only as SHA-256 digests centrally. Sensitive authentication/enrollment endpoints are rate limited. CSP, nosniff, frame denial, bounded request/artifact content, role/owner checks and audit events are included. TLS/Tailscale is required for sensitive use over untrusted networks.

## API map

- `GET /health`: readiness without credentials.
- `POST /api/v1/auth/login`, `/logout`, `/password`; `GET /auth/me`.
- `POST /api/v1/enrollment-codes`, `/workers/enroll`.
- `POST /api/v1/workers/{id}/heartbeat`, `/jobs/claim`, `/control`, `/revoke`; `PUT /workers/{id}/preferences` (versioned owner settings).
- `POST /api/v1/attempts/{id}/progress`, `/uploads`, `/release`, `/fail`, `/complete`.
- `PUT /api/v1/uploads/{id}?offset=N`; `GET /uploads/{id}` returns offset; `POST /uploads/{id}/finalize`.
- `GET /api/v1/overview`, `/workers`, `/workers/{id}`, `/studies`, `/experiments`, `/experiments/{id}`, `/checkpoints`, `/events`, `/events/download`, `/settings`.
- `POST /api/v1/studies`; `POST /studies/{id}/start|pause|resume`; `PUT /settings`.
- `GET /api/v1/artifacts/{id}/download` with scoped download permission.
- `GET /api/v1/stream`: authenticated fetch-based SSE, 10s polling fallback in the UI.

## Known boundaries

Single coordinator; local disk; trusted research workers and approved code; no arbitrary uploaded Python or shell commands; no generic task execution. A manifest's path arguments are selected by the administrator, not by untrusted workers. This release does not automatically distribute licensed data or mutate drivers, power settings or institutional firewalls. Coordinators validate checkpoint envelopes without loading PyTorch, while workers perform full safe-state validation. Owner-specific optional time windows and benchmark-proven multi-GPU concurrency are future extensions; they are not advertised as operational controls.
