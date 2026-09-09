# scheduling Specification

## Purpose

Defines cronbook's scheduling model: the single dispatcher heartbeat and the
scheduler backends that can carry it (a fenced crontab section, or a per-user
launchd agent on macOS), install / uninstall and backend selection, portable
crontab manipulation, launchd agent provisioning, dispatch of due jobs on each
tick, tick liveness recording, timezone evaluation, per-minute dedupe,
resilience, and dispatcher logging.

## Requirements

### Requirement: Single dispatcher heartbeat
cronbook SHALL manage its scheduling through a single scheduler backend that invokes
`<abs>/cronbook tick` at least once per wall-clock minute, using the absolute path to the
cronbook executable. The backend SHALL be either a fenced, cronbook-managed section in the user's
crontab holding the line `* * * * * <abs>/cronbook tick`, or a per-user launchd agent running
the same command on a fixed interval. Because dispatch is deduped per wall-clock minute, a
backend MAY tick more than once in a minute; it SHALL NOT leave a minute without a tick under
normal operation. The heartbeat SHALL be written once at install and SHALL NOT be rewritten
when jobs are added, updated, deleted, enabled, or disabled. When a non-default config path is
in use, cronbook SHALL embed `--config-toml <path>` into the invocation regardless of backend.

#### Scenario: Heartbeat installed under the cron backend
- **WHEN** cronbook is installed with the cron backend
- **THEN** the user's crontab contains exactly one fenced `* * * * * <abs>/cronbook tick` line

#### Scenario: Heartbeat installed under the launchd backend
- **WHEN** cronbook is installed with the launchd backend
- **THEN** a per-user launchd agent is provisioned that runs `<abs>/cronbook tick` at least once per
  wall-clock minute
- **AND** the user's crontab is not modified

#### Scenario: Job changes do not touch the heartbeat
- **WHEN** a user adds, updates, deletes, enables, or disables a job
- **THEN** neither the crontab nor the launchd agent is modified

#### Scenario: Non-default config is propagated
- **WHEN** cronbook is installed with a non-default config path
- **THEN** the heartbeat invocation includes `--config-toml <path>` so the dispatcher and its workers
  read the same config, under either backend

### Requirement: Install and uninstall
cronbook SHALL provide a way to install the heartbeat and a way to uninstall it. Install SHALL
accept a backend selection of `auto`, `cron`, or `launchd`, defaulting to `auto`. Under `auto`
cronbook SHALL select the launchd backend on macOS and the cron backend on every other platform.
Selecting `launchd` on a non-macOS platform SHALL fail with a clear error rather than falling
back silently. Install SHALL succeed even when the invoking user has no existing crontab and no
existing `~/Library/LaunchAgents` directory, and SHALL be idempotent: reinstalling with the same
backend refreshes the heartbeat in place instead of creating a second one.

Exactly one backend SHALL be installed at a time. Installing one backend while a different one is
already installed SHALL remove the other, so switching backends is a single command and two
heartbeats never tick the same database concurrently. Install SHALL report a backend it removed
this way.

Uninstall SHALL take no backend selection. It SHALL detect which backends are actually present
and remove every one it finds, so a heartbeat installed under one backend is never left running
after an uninstall issued under a different assumption. Uninstall SHALL remove the cronbook-managed
crontab section while leaving the user's other crontab entries intact, and SHALL be a no-op that
succeeds when no backend is installed.

#### Scenario: Installing with no prior crontab
- **WHEN** a user installs cronbook with the cron backend and has no existing crontab
- **THEN** a crontab is created containing the cronbook-managed section

#### Scenario: Default backend on macOS
- **WHEN** a user installs cronbook on macOS without selecting a backend
- **THEN** the launchd backend is used

#### Scenario: Default backend off macOS
- **WHEN** a user installs cronbook on a non-macOS platform without selecting a backend
- **THEN** the cron backend is used

#### Scenario: launchd requested off macOS
- **WHEN** a user requests the launchd backend on a non-macOS platform
- **THEN** cronbook reports a clear error and installs nothing

#### Scenario: Reinstalling is idempotent
- **WHEN** a user installs cronbook twice with the same backend
- **THEN** exactly one heartbeat exists afterwards, refreshed to the current executable and config path

#### Scenario: Switching backends replaces the previous one
- **WHEN** a user installs cronbook with one backend while the other backend is already installed
- **THEN** the previously installed backend is removed and only the newly selected one remains
- **AND** the removal is reported

#### Scenario: Uninstalling removes whichever backend is present
- **WHEN** a user installs cronbook under one backend and later runs uninstall without any backend selection
- **THEN** the installed heartbeat is removed and no tick remains scheduled

#### Scenario: Uninstalling with both backends present
- **WHEN** both a cronbook crontab section and a cronbook launchd agent exist
- **THEN** uninstall removes both

#### Scenario: Uninstalling when nothing is installed
- **WHEN** a user runs uninstall with no cronbook heartbeat installed
- **THEN** the command succeeds without error and changes nothing

#### Scenario: Other crontab entries preserved on uninstall
- **WHEN** a user uninstalls cronbook and the crontab holds unrelated entries
- **THEN** the cronbook-managed section is removed and other crontab entries are preserved

### Requirement: Portable crontab manipulation
cronbook SHALL read and write the crontab portably across macOS (BSD cron) and Linux
(cronie/vixie) using the `crontab` command: reading the current crontab with `crontab -l`,
editing the fenced section in memory, and writing the result back via stdin (`crontab -`).
cronbook SHALL detect the "no crontab yet" condition by the non-zero exit status of `crontab
-l` (not by matching message text) and treat it as an empty crontab. cronbook SHALL NOT use
`crontab -e` (interactive) or `crontab -r` (remove-all).

#### Scenario: No existing crontab detected by exit code
- **WHEN** `crontab -l` exits non-zero because the user has no crontab
- **THEN** cronbook treats the crontab as empty rather than failing

#### Scenario: Other entries preserved on write
- **WHEN** cronbook writes the crontab back after editing its fenced section
- **THEN** all non-cronbook entries are preserved unchanged

### Requirement: Surface cron environment problems
cronbook SHALL surface a clear, actionable error when a `crontab` operation fails due to
insufficient permissions (e.g. a user not permitted to use cron), rather than failing
silently.

#### Scenario: crontab operation denied
- **WHEN** a `crontab` install or uninstall operation is denied by the system
- **THEN** cronbook reports a clear error explaining the failure

### Requirement: launchd heartbeat backend
On macOS, cronbook SHALL provision the heartbeat as a per-user launchd agent: a property list
written to `~/Library/LaunchAgents/` whose file name matches its `Label`, invoking the absolute
cronbook executable with the `tick` argument (and `--config-toml <path>` when a non-default config
is in use) on a fixed interval short enough that every wall-clock minute receives at least one
tick despite launchd timer drift and coalescing. cronbook SHALL load the agent into the user's own GUI domain
so the tick, and therefore every job it spawns, runs inside the user's login session. cronbook
SHALL unload the agent before rewriting its plist so a reinstall takes effect without a logout,
and SHALL unload it and delete the plist on uninstall.

cronbook SHALL own only its own agent: it SHALL NOT read, modify, or remove any other plist in
`~/Library/LaunchAgents/`.

#### Scenario: Agent provisioned on install
- **WHEN** a user installs cronbook with the launchd backend
- **THEN** a plist named after cronbook's label exists in `~/Library/LaunchAgents/`
- **AND** it invokes the absolute cronbook executable with `tick` on a repeating interval
- **AND** the agent is loaded into the user's GUI domain

#### Scenario: Every wall-clock minute is ticked
- **WHEN** the launchd agent runs over a period of many minutes
- **THEN** each wall-clock minute receives at least one tick
- **AND** any extra tick within the same minute dispatches nothing, because dispatch is deduped per
  minute

#### Scenario: Tick runs in the user session
- **WHEN** the heartbeat runs under the launchd backend
- **THEN** the tick process runs in the user's login session, so jobs it spawns inherit that
  session's environment, including the SSH agent socket

#### Scenario: Reinstall replaces a loaded agent
- **WHEN** a user reinstalls cronbook with the launchd backend while the agent is already loaded
- **THEN** the old agent is unloaded, the plist is rewritten, and the new agent is loaded

#### Scenario: Agent removed on uninstall
- **WHEN** a user uninstalls cronbook and a launchd agent is present
- **THEN** the agent is unloaded and its plist is deleted from `~/Library/LaunchAgents/`

#### Scenario: Foreign agents untouched
- **WHEN** cronbook installs or uninstalls its launchd agent
- **THEN** every other plist in `~/Library/LaunchAgents/` is left unchanged

### Requirement: The tick records when it last ran
Each `cronbook tick` SHALL record the time it ran, so heartbeat liveness is observable without
reading logs or querying the scheduler backend. The timestamp SHALL be recorded at the start of
the tick, before dispatch, so it reflects that the heartbeat fired even when dispatch later
fails. It SHALL be stored as a single value that each tick overwrites - not accumulated history -
and SHALL be readable independently of whether any job was due.

#### Scenario: Tick records its time
- **WHEN** `cronbook tick` runs
- **THEN** the recorded last-tick time is updated to that tick's time

#### Scenario: Recorded even when nothing is due
- **WHEN** `cronbook tick` runs and no job is due
- **THEN** the last-tick time is still updated

#### Scenario: Recorded even when dispatch fails
- **WHEN** `cronbook tick` records its time and dispatch subsequently fails
- **THEN** the recorded last-tick time still reflects that the tick fired

#### Scenario: No last tick before the first tick
- **WHEN** no tick has ever run
- **THEN** the last-tick time reads as absent rather than as a default or zero time

### Requirement: Surface launchd provisioning problems
cronbook SHALL surface a clear, actionable error when provisioning or removing the launchd agent
fails - because `launchctl` is unavailable, because the plist cannot be written, or because a
`launchctl` invocation exits non-zero - rather than reporting a successful install. cronbook SHALL
determine `launchctl` outcomes from exit status rather than by matching message text.

#### Scenario: launchctl unavailable
- **WHEN** the `launchctl` command cannot be found
- **THEN** cronbook reports a clear error explaining the failure and does not report a successful install

#### Scenario: launchctl rejects the agent
- **WHEN** a `launchctl` load or unload invocation exits non-zero
- **THEN** cronbook reports a clear error including the reason reported by `launchctl`

#### Scenario: Plist cannot be written
- **WHEN** the plist cannot be written to `~/Library/LaunchAgents/`
- **THEN** cronbook reports a clear error naming the path and the underlying reason

### Requirement: Dispatch of due jobs
On each invocation, `cronbook tick` SHALL first reconcile stale runs (see crash reconciliation),
then read all enabled job definitions from the repository, determine which jobs are due for the
current wall-clock minute, and submit each due job: it SHALL atomically claim a run (honoring the
no-overlap rule - skip if a run of that job is in flight - and the global concurrency cap) and
spawn a worker (`cronbook run <run-id>`) only for a run that actually starts. A due run blocked
because a run is already in flight or the cap is reached SHALL be recorded `skipped` without
spawning a worker. The tick SHALL perform only reconciliation and submission and then exit;
workers SHALL run independently of the tick process.

#### Scenario: A due job is dispatched
- **WHEN** the tick runs during a minute matching an enabled job's schedule and no run of that
  job is in flight
- **THEN** a run is claimed and a worker is spawned for it

#### Scenario: A disabled job is not dispatched
- **WHEN** the tick runs during a minute matching a disabled job's schedule
- **THEN** no run is claimed and no worker is spawned for that job

#### Scenario: A blocked due job is skipped without a worker
- **WHEN** the tick runs during a minute matching an enabled job whose previous run is still in
  flight
- **THEN** the new run is recorded `skipped` and no worker is spawned

### Requirement: Reconcile crashed runs on each tick
On each invocation, before determining which jobs are due, `cronbook tick` SHALL reconcile stale
runs per the lease-liveness rule: any run recorded `running` whose lease has expired SHALL be
recorded as `crashed`. Reconciliation SHALL only update run status; the tick SHALL NOT
re-execute or retry a reconciled run. Because reconciliation runs before due-job evaluation, a
run freed by reconciliation SHALL no longer block a due job by the no-overlap rule nor count
against the global concurrency cap within that same tick. A failure to reconcile a particular run
SHALL be logged to the internal log and SHALL NOT derail reconciling the others or dispatching
due jobs.

#### Scenario: A crashed run is reconciled on tick
- **WHEN** the tick runs while a run recorded `running` has an expired lease
- **THEN** that run is recorded as `crashed` and no worker is spawned to retry it

#### Scenario: Reconciliation unblocks a due job in the same tick
- **WHEN** the tick runs during a minute matching an enabled job whose only in-flight run has an
  expired lease
- **THEN** the crashed run is reconciled and a fresh scheduled run is claimed and dispatched for
  the current minute

#### Scenario: A live run is not reconciled
- **WHEN** the tick runs while a job's run is `running` with an unexpired lease
- **THEN** that run is left `running` and is not reconciled

### Requirement: Schedule evaluation timezone
The dispatcher SHALL evaluate a job's cron expression in the machine's local timezone by
default. If a job specifies a timezone, the dispatcher SHALL evaluate that job's schedule in
the specified timezone. Different jobs MAY use different timezones.

#### Scenario: Default local-time evaluation
- **WHEN** a job with no timezone set has schedule `0 2 * * *`
- **THEN** the dispatcher considers it due at 02:00 local time

#### Scenario: Per-job timezone override
- **WHEN** a job specifies timezone `America/Los_Angeles`
- **THEN** the dispatcher evaluates that job's schedule in `America/Los_Angeles`

### Requirement: Per-minute dispatch dedupe
The dispatcher SHALL record, per job, the last minute it dispatched that job, and SHALL NOT
dispatch a job more than once for the same wall-clock minute even if the tick re-runs or
overlaps. Schedule matching SHALL be anchored to the minute (seconds floored) so a tick that
fires slightly late still matches the intended minute.

#### Scenario: No double-fire on a repeated tick
- **WHEN** two ticks run for the same wall-clock minute
- **THEN** a job due that minute is dispatched only once

#### Scenario: Late tick still matches its minute
- **WHEN** a tick fires a few seconds after the start of a minute
- **THEN** jobs due for that minute are still dispatched

### Requirement: Resilience to bad schedules and tick failure
A malformed cron expression on one job SHALL cause only that job to be skipped, with the error
logged, without affecting dispatch of other jobs. Manual execution via `cronbook trigger` SHALL
continue to work even if the heartbeat line is absent.

#### Scenario: One bad expression does not block others
- **WHEN** one enabled job has an unparseable cron expression during a tick
- **THEN** that job is skipped and logged, and other due jobs are still dispatched

#### Scenario: Manual run without heartbeat
- **WHEN** the heartbeat line has been removed but a user runs `cronbook trigger` for a job
- **THEN** the job still executes

### Requirement: Dedicated internal log for dispatcher errors
The dispatcher SHALL write tick-level errors (e.g. unparseable schedules, unreadable database,
spawn failures) to a dedicated internal log directory (`internal_log_dir`) that is separate
from the per-run job logs under `log_dir`. Internal logs SHALL NOT be mixed with job output.

#### Scenario: Tick error goes to the internal log
- **WHEN** a tick encounters an error (such as a malformed schedule or a database problem)
- **THEN** the error is recorded in the internal log directory and not in any job's run log
