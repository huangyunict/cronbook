# run-execution Specification

## Purpose

Defines how a claimed run is executed and recorded: process spawning, timeouts,
run status taxonomy, overlap and concurrency enforcement, manual triggers,
killing runs, and operational logging of the run lifecycle.

## Requirements

### Requirement: Executor runs a claimed run and records the outcome
`cronbook run <run-id>` SHALL execute an already-claimed run - one the submitter (the dispatcher
or a manual trigger) has recorded as `running`. A run's id SHALL be a system-generated UUID
rendered in its canonical dashed form (e.g. `edbeb0ee-a076-41b9-8343-8be12bd44354`). It SHALL load
the run and its job, take ownership
of the run (recording its `owner`), spawn the job in its own process group (via `setsid`), apply
the job's configured working directory and environment variables, capture the job's stdout/stderr,
renew the run's lease on a heartbeat while it runs, and record the run's terminal outcome
including its start time, end time, exit code, and process-group id. Deciding whether a run may
start - the atomic claim - is performed by the submitter, not the executor.

#### Scenario: A run is recorded
- **WHEN** the executor runs a claimed run to completion
- **THEN** the run row records start time, end time, exit code, and captured output location

#### Scenario: Job environment is applied
- **WHEN** the executor runs a job that has a configured working directory and environment
- **THEN** the job process runs in that working directory with those environment variables

### Requirement: Per-job timeout
Each job SHALL have a timeout whose default is unlimited (no timeout). A user MAY set a specific
timeout duration. When a run exceeds its job's timeout, the executor SHALL terminate the run
using the same process-group kill path (`TERM` then `KILL` after a grace period) and record the
run with status `timeout`.

#### Scenario: No timeout by default
- **WHEN** a job with no configured timeout runs longer than any fixed duration
- **THEN** the run is not terminated on account of a timeout

#### Scenario: Timeout exceeded
- **WHEN** a job with a configured timeout runs longer than that timeout
- **THEN** the run's process group is terminated and the run is recorded as `timeout`

### Requirement: Run status taxonomy
Each run SHALL have a status drawn from: `running`, `success`, `failed`, `timeout`,
`killed`, `skipped`, and `crashed`. A completed run SHALL be `success` when its exit code is 0
and `failed` otherwise. A run whose lease expires while still `running` SHALL be reconciled to
`crashed`. Each run SHALL be tagged with its source as either `scheduled` or `manual`.

#### Scenario: Successful completion
- **WHEN** a job exits with code 0
- **THEN** its run status is `success`

#### Scenario: Non-zero completion
- **WHEN** a job exits with a non-zero code
- **THEN** its run status is `failed`

#### Scenario: Expired lease becomes crashed
- **WHEN** a run recorded `running` has an expired lease and is reconciled
- **THEN** its status becomes `crashed`

### Requirement: No overlapping runs of the same job
Two runs of the same job id SHALL NOT execute at the same time, whether dispatched or manually
started. When a new run would start while a run of the same job id is in flight (per the
lease-liveness predicate), the new run SHALL be recorded `skipped` and SHALL NOT start. There is
no per-job overlap policy and no kill-previous behavior; skipping is unconditional. The overlap
check SHALL be atomic - checking for an existing in-flight run and inserting the new run row in a
single transaction - so concurrent submitters cannot both start.

#### Scenario: Skip when already running
- **WHEN** a job is triggered or dispatched while a run of the same id is in flight
- **THEN** the new run is recorded as `skipped` and does not start

#### Scenario: Concurrent submitters do not both start
- **WHEN** a scheduled dispatch and a manual trigger for the same job id occur at nearly the
  same time
- **THEN** at most one run starts and the other is recorded `skipped`, never both running

#### Scenario: A stale in-flight run does not block forever
- **WHEN** a job's only in-flight run has an expired lease
- **THEN** a new run of that job is not skipped on its account (the expired run is not in flight)

### Requirement: Global concurrency cap
cronbook SHALL enforce a global hard cap on simultaneously running jobs (`max_concurrent_runs`),
counting only runs that are in flight per the lease-liveness predicate. A run that would exceed
the cap SHALL be recorded as `skipped` rather than started. A run whose lease has expired SHALL
NOT count against the cap.

#### Scenario: Cap reached
- **WHEN** starting a new run would exceed `max_concurrent_runs` in-flight runs
- **THEN** the new run is recorded as `skipped` and does not start

#### Scenario: Expired lease frees a slot
- **WHEN** a counted run's lease expires
- **THEN** it no longer counts against `max_concurrent_runs`

### Requirement: List running jobs with liveness reconciliation
The CLI SHALL list currently running jobs, showing each running run's run id, cron job id, and
other relevant information. A run SHALL be reported as running only if it is in flight per the
lease-liveness predicate (status `running` and lease unexpired); runs whose lease has expired
SHALL be reconciled to `crashed` rather than reported as running.

#### Scenario: Listing live runs
- **WHEN** a user lists running jobs
- **THEN** the output includes each in-flight run's run id and cron job id

#### Scenario: Stale running row is reconciled
- **WHEN** a run recorded `running` has an expired lease
- **THEN** listing running jobs reconciles that run to `crashed` instead of showing it as running

### Requirement: Trigger a job immediately
The CLI SHALL trigger a job to run immediately, by id or name. The manual run SHALL be tagged
`manual` and SHALL be subject to the no-overlap rule (skipped if a run of that id is in flight).
There is no kill-previous option. A manual trigger SHALL execute even if the job is disabled -
manual execution overrides the enabled flag.

#### Scenario: Manual trigger
- **WHEN** a user triggers a job and no run of that id is in flight
- **THEN** a run tagged `manual` starts

#### Scenario: Manual trigger while a run is in flight
- **WHEN** a user triggers a job while a run of that id is in flight
- **THEN** the manual run is recorded `skipped` and does not start

#### Scenario: Manual trigger of a disabled job
- **WHEN** a user triggers a disabled job
- **THEN** the job runs anyway (the disabled flag is overridden for the manual run) and the run
  is tagged `manual`

### Requirement: Kill a running job
The CLI SHALL kill a running job and record it with status `killed`. How the job's process is
terminated depends on whether its worker is alive (per the lease-liveness predicate):

- **Worker alive (unexpired lease):** the kill SHALL be cooperative - it SHALL mark the run
  `killed` (revoking its lease) rather than signal the process directly, and the owning worker,
  observing on its next heartbeat that it is no longer the running owner, SHALL terminate its own
  process group (`TERM` then `KILL` after a grace period so children are not orphaned). The
  command SHALL inform the user that the kill is cooperative and may take up to roughly one
  heartbeat interval plus the grace period to take effect, rather than reporting the process as
  already dead.
- **Worker not alive (expired lease / orphaned job):** because no live worker remains to act on a
  cooperative signal, the command SHALL directly terminate the recorded process group (`TERM`
  then `KILL` after a grace period) so an orphaned job is not left running, and record the run
  `killed`.

#### Scenario: Cooperative kill of a live run
- **WHEN** a user kills a running job whose worker is alive
- **THEN** the run is marked `killed`, the command reports that the kill is cooperative, and the
  owning worker terminates its process group within roughly one heartbeat interval plus the grace
  period

#### Scenario: Direct reap of an orphaned run
- **WHEN** a user kills a run whose lease has expired (its worker is no longer alive) but whose
  process group is still recorded
- **THEN** the command directly terminates that process group and records the run as `killed`

### Requirement: Operational logging of the run lifecycle
The run service SHALL emit operational (diagnostic) log records for a run's lifecycle through a
logging framework, keeping them out of both the process's stdout/stderr and the run's own
captured output. As unattended, library-style code the run service SHALL NOT assume ownership of
stdout/stderr; the application entry point configures the handlers and destination, which SHALL
default to the dedicated `internal_log_dir` - the same operational-log area as dispatcher/tick
errors - and never `app_log_dir` (per-run job output). The lifecycle records SHALL cover at
least the run's claim outcome (started, or skipped because a run is already in flight or the
concurrency cap is reached), the spawned process (pid and process-group id), lease events
relevant to termination (cooperative-kill lease revocation, self-fence, and lease-expiry crash
reconciliation), timeout termination, and the run's finalization (terminal status and exit code);
a failure to execute (e.g. an unknown job or a spawn failure) SHALL be logged at error level.
These records are diagnostics only - the authoritative record of a run remains its repository
row, and the job's own output remains under `app_log_dir`.

#### Scenario: Lifecycle events go to the operational log
- **WHEN** the run service runs a job to completion
- **THEN** its lifecycle (claim, spawn, finalization) is emitted through the logging framework to
  the internal operational log and not into the job's captured output

#### Scenario: A skipped run is logged with its reason
- **WHEN** a run is skipped because a run is already in flight or the concurrency cap is reached
- **THEN** the skip and its reason are recorded in the operational log

#### Scenario: Diagnostics never appear in job output
- **WHEN** the run service logs lifecycle or error events
- **THEN** none of them appear in the run's captured stdout/stderr under `app_log_dir`

### Requirement: Lease-based run liveness with worker heartbeat
A run's liveness SHALL be governed by a time-bounded lease rather than by probing its operating
system process. When a run is claimed it SHALL be assigned a `lease_expires_at` a lease-TTL into
the future. The worker that executes the run SHALL take ownership by recording an `owner`
identity and SHALL renew the lease at a fixed heartbeat interval for as long as the job runs. The
lease TTL and heartbeat interval SHALL be fixed internal constants - a lease TTL of 30 seconds
and a heartbeat interval of 5 seconds - and SHALL NOT be user-configurable.

A run SHALL be considered in flight if and only if its status is `running` AND its
`lease_expires_at` is in the future. Every place that reasons about in-flight runs - the overlap
check, the concurrency cap, and the running-jobs listing - SHALL use this predicate, so a run
whose lease has expired is treated as not in flight even before its status has been reconciled.

A worker SHALL guard every update it makes to its run on the run still being `running` and owned
by it (owner-guard). If a guarded update matches no row - because the run was reconciled to a
terminal status, or its lease was revoked and the run re-owned - the worker SHALL treat itself as
fenced: it SHALL terminate its job's process group and stop, and SHALL NOT record the run as
completed. A worker that cannot renew its lease for longer than the lease TTL (loss of contact
with the store) SHALL likewise terminate its job and stop, so a crash can never produce two
concurrent executions of the same run.

The recorded process-group id SHALL be retained and used to terminate a job locally (timeout,
self-fence, cooperative kill); it SHALL NOT be used to decide liveness.

Note: on the current single-machine SQLite deployment all processes share one wall clock, so
lease timestamps are mutually consistent. A future shared-store deployment MUST evaluate lease
time against a single authoritative (server) clock.

#### Scenario: Lease renewed while running
- **WHEN** a worker is executing its job and the heartbeat interval elapses
- **THEN** it renews the run's `lease_expires_at` and the run remains in flight

#### Scenario: Expired lease is not in flight
- **WHEN** a run's status is `running` but its `lease_expires_at` is in the past
- **THEN** the run is treated as not in flight by the overlap check, the concurrency cap, and the
  running-jobs listing, regardless of whether its status has been reconciled yet

#### Scenario: A fenced worker stops without completing
- **WHEN** a worker's guarded update matches no row (the run was reconciled or re-owned)
- **THEN** the worker terminates its job's process group and stops without recording the run as
  completed

#### Scenario: A worker that loses contact stops
- **WHEN** a worker cannot renew its lease for longer than the lease TTL
- **THEN** it terminates its job and stops, so the run cannot execute twice
