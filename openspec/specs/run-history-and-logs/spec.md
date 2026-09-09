# run-history-and-logs Specification

## Purpose

Defines run-history retrieval, log capture and retrieval, log size capping,
timestamp handling, and the v1 retention policy - including bounding the
scheduler log captured from the dispatcher heartbeat.

## Requirements

### Requirement: Show recent runs
The CLI SHALL show recent runs, including each run's id, its job's id and name, status, source
(`scheduled`/`manual`), and timing. Both the job id and the job name SHALL be shown regardless
of whether a job selector was provided. Manual runs SHALL count toward these runs. The number
of runs shown SHALL default to 5 and SHALL be overridable with `--limit <n>`. A job selector
(`--job-id`/`--job-name`) SHALL be optional: when a selector is given the runs are scoped to
that job; when no selector is given the most recent runs across all jobs are shown.

#### Scenario: Showing recent runs of a job
- **WHEN** a user requests the recent runs of a job that has run more than the limit
- **THEN** the most recent runs up to the limit are shown, most recent first, each labeled with
  its job id and name

#### Scenario: Limiting the number of runs
- **WHEN** a user passes `--limit <n>`
- **THEN** at most `n` runs are shown, and when `--limit` is omitted at most 5 are shown

#### Scenario: Showing runs across all jobs
- **WHEN** a user requests recent runs with neither `--job-id` nor `--job-name`
- **THEN** the most recent runs across all jobs are shown, most recent first, each labeled with
  its job id and name

#### Scenario: Manual runs are included
- **WHEN** a job's recent runs include manually triggered runs
- **THEN** those manual runs appear in the list tagged as `manual`

### Requirement: Log capture to disk with metadata in the DB
Each run's stdout/stderr SHALL be captured to a log file on disk under the configured log
directory, while the repository stores only metadata (log path, size, exit code, timing). Log
files and the repository database SHALL be created with `0600` permissions.

#### Scenario: Output captured to a file
- **WHEN** a job run produces stdout and stderr
- **THEN** the output is written to a log file on disk and the run row stores that file's path
  and metadata

#### Scenario: Restrictive permissions
- **WHEN** a log file or the repository database is created
- **THEN** it is created with `0600` permissions

### Requirement: Log size cap keeps the head and tail
A run's captured log SHALL be capped by retaining the first `max_head_log_lines` lines (the
head) and the last `max_tail_log_lines` lines (the tail). When a run produces at most
`max_head_log_lines` + `max_tail_log_lines` lines, the entire output SHALL be retained
unchanged. When it produces more, the head and tail SHALL be retained and the lines between
them SHALL be dropped and replaced with a single marker line indicating how many lines were
omitted.

#### Scenario: Output within the cap
- **WHEN** a run produces no more than `max_head_log_lines` + `max_tail_log_lines` lines
- **THEN** the stored log retains the complete output with no lines dropped

#### Scenario: Exceeding the cap
- **WHEN** a run produces more lines than `max_head_log_lines` + `max_tail_log_lines`
- **THEN** the stored log retains the first `max_head_log_lines` lines and the last
  `max_tail_log_lines` lines, with a marker line in place of the omitted middle noting how many
  lines were dropped

### Requirement: Output the logs of a run
The CLI SHALL output the logs of a run instance given its run id.

#### Scenario: Viewing a run's logs
- **WHEN** a user requests the logs for a valid run id
- **THEN** the CLI outputs that run's captured stdout/stderr

#### Scenario: Unknown run id
- **WHEN** a user requests logs for a run id that does not exist
- **THEN** the CLI reports an error and exits non-zero

### Requirement: Timestamps stored in UTC
All timestamps recorded in the repository SHALL be stored in UTC. Frontends SHALL render
timestamps in the machine's local timezone with the timezone indicated.

#### Scenario: UTC storage, local display
- **WHEN** a run's start and end times are recorded and later displayed
- **THEN** they are stored in UTC and rendered in local time with the timezone shown

### Requirement: Retention is enforced by prune
cronbook SHALL NOT prune run history, log files, deleted-job trash, or the captured scheduler log
except through the `prune` operation, which enforces the configured retention settings (each
taking its default when absent). `prune` SHALL retain, per job, only the most recent
`keep_last_runs` runs (ordered most-recent-first) and SHALL remove older runs' repository rows
together with their on-disk log files. `prune` SHALL delete trashed deleted-job log directories
whose age exceeds `trash_retention_days`. `prune` SHALL NOT remove a run that is in flight
(recorded `running` with an unexpired lease) or its log, regardless of `keep_last_runs`, so
retention never disturbs a live run.

`prune` SHALL additionally bound the captured scheduler log - the file a scheduler backend
redirects the tick's stderr to - by rotating it to a single previous generation once it exceeds a
fixed internal size cap, replacing any previous generation. On-disk scheduler log content is
thereby bounded at roughly twice that cap without a configuration setting. `prune` SHALL leave the
file untouched while it is within the cap, and SHALL treat its absence as nothing to do.

#### Scenario: Pruning run history beyond keep_last_runs
- **WHEN** a job has more terminal runs than `keep_last_runs`
- **THEN** `prune` keeps the most recent `keep_last_runs` runs and removes the older runs' rows and their
  log files

#### Scenario: History within keep_last_runs is retained
- **WHEN** a job has no more runs than `keep_last_runs`
- **THEN** `prune` removes none of that job's runs

#### Scenario: In-flight runs are never pruned
- **WHEN** a job has an in-flight run (running with an unexpired lease) that would otherwise fall
  outside `keep_last_runs`
- **THEN** `prune` does not remove that run or its log

#### Scenario: Expiring old trash
- **WHEN** a trashed deleted-job log directory is older than `trash_retention_days`
- **THEN** `prune` permanently deletes that trashed directory

#### Scenario: Rotating an oversized scheduler log
- **WHEN** the captured scheduler log exceeds the internal size cap
- **THEN** `prune` rotates it to a single previous generation and the active file restarts empty
- **AND** any previous generation is replaced, so at most two generations exist

#### Scenario: Scheduler log within the cap is left alone
- **WHEN** the captured scheduler log is within the internal size cap
- **THEN** `prune` does not rotate or truncate it

#### Scenario: No scheduler log present
- **WHEN** no captured scheduler log exists, because the backend in use does not write one
- **THEN** `prune` succeeds and reports no rotation

### Requirement: prune reports what it removed
The `prune` operation SHALL report the outcome of its sweep: the number of run rows removed, the
trashed directories deleted, and whether the captured scheduler log was rotated, and SHALL support
a dry-run mode that computes and reports the same outcome without removing, rotating, or otherwise
modifying anything.

#### Scenario: Reporting removals
- **WHEN** `prune` runs and prunes runs and/or trash
- **THEN** it reports how many runs and trashed directories were removed

#### Scenario: Reporting a scheduler log rotation
- **WHEN** `prune` rotates the captured scheduler log
- **THEN** it reports that the rotation happened

#### Scenario: Dry run removes nothing
- **WHEN** `prune` runs in dry-run mode
- **THEN** it reports the runs, trashed directories, and scheduler log rotation that would have
  happened, and the on-disk state is unchanged

### Requirement: prune runs automatically during tick
`cronbook tick` SHALL invoke `prune` automatically, throttled so the sweep runs at most once per a
fixed internal interval and so it never prevents or delays the dispatch of due jobs. A failure
of the automatic sweep SHALL NOT abort the tick's dispatch of due jobs.

#### Scenario: Throttled automatic sweep
- **WHEN** ticks occur more frequently than the prune throttle interval
- **THEN** at most one automatic prune sweep runs per interval

#### Scenario: Dispatch is unaffected by prune failure
- **WHEN** the automatic prune sweep raises an error during a tick
- **THEN** the tick still dispatches the due jobs and records the prune failure without failing the
  tick
