# cli Specification

## Purpose

Defines the `cronbook` command-line interface: the command surface, how jobs and
runs are selected, and the human-readable and machine-readable (`--json`) output
contracts.

## Requirements

### Requirement: Command surface
The `cronbook` CLI SHALL provide commands to: list scheduled jobs (the `jobs` command), list
running jobs, show the last 5 runs of a job, output the logs of a run, add a job, update a job,
delete a job, enable a job, disable a job, trigger a job to run immediately, kill a running job,
import job config from JSON, export job config to JSON, prune old run history and expired trash
per the retention settings (the `prune` command), report the state of the dispatcher heartbeat
(the `status` command), and install / uninstall the dispatcher heartbeat using a
platform-appropriate scheduler backend. The `prune` command SHALL enforce the
configured retention settings and SHALL accept `--dry-run` to report what would be removed without
removing anything. The `install` command SHALL accept `--scheduler` with the values `auto`, `cron`,
and `launchd`, defaulting to `auto`, and SHALL reject any other value. The `uninstall` command
SHALL NOT accept a backend option.

#### Scenario: Listing available commands
- **WHEN** a user runs `cronbook --help`
- **THEN** the CLI lists all supported commands and a short description of each
- **AND** the list of scheduled jobs is provided by a command named `jobs`

#### Scenario: Unknown command
- **WHEN** a user runs `cronbook` with an unrecognized command
- **THEN** the CLI prints an error and exits with a non-zero status

#### Scenario: Running retention pruning
- **WHEN** a user runs `cronbook prune`
- **THEN** the CLI enforces the configured retention and reports how many runs and trashed
  directories were removed, and whether the captured scheduler log was rotated

#### Scenario: Prune dry run
- **WHEN** a user runs `cronbook prune --dry-run`
- **THEN** the CLI reports what would be removed and removes nothing

#### Scenario: Scheduler option documented with its default
- **WHEN** a user runs `cronbook install --help`
- **THEN** the help text lists the `auto`, `cron`, and `launchd` choices and states that the default
  `auto` selects launchd on macOS and cron elsewhere

#### Scenario: Invalid scheduler value
- **WHEN** a user runs `cronbook install --scheduler=<unsupported>`
- **THEN** the CLI prints an error and exits with a non-zero status without installing anything

### Requirement: Install and uninstall report the scheduler backend
The `install` and `uninstall` commands SHALL name the backend they acted on, so the effect of
`auto` and of auto-detecting uninstall is visible rather than inferred. In default mode the
status line SHALL name the backend; under `--json` the result object SHALL carry it as a field.
Uninstall SHALL report every backend it removed, and SHALL report that nothing was installed when
it finds no heartbeat.

#### Scenario: Install names the resolved backend
- **WHEN** a user runs `cronbook install` without `--json`
- **THEN** the status line on stderr names the backend that was installed

#### Scenario: Install reports the backend as JSON
- **WHEN** a user runs `cronbook install --json`
- **THEN** the result object on stdout includes the resolved backend

#### Scenario: Install reports replacing a different backend
- **WHEN** a user installs one backend while the other is already installed
- **THEN** the output names both the backend that was installed and the one that was replaced

#### Scenario: Uninstall names what it removed
- **WHEN** a user runs `cronbook uninstall` and a heartbeat is present
- **THEN** the output names each backend that was removed

#### Scenario: Uninstall reports finding nothing
- **WHEN** a user runs `cronbook uninstall` with no heartbeat installed
- **THEN** the output states that no heartbeat was installed

### Requirement: status reports the heartbeat state
The CLI SHALL provide a read-only `status` command that reports which scheduler backend is
installed, if any, and when the dispatcher last ticked. It SHALL change no state. Being a read
command, its data SHALL go to stdout in both default and `--json` mode: a human-readable summary
by default, and the same fields as a result object under `--json`. `status` SHALL report the last
tick as an absolute local timestamp with the timezone shown, consistent with other rendered
timestamps, alongside its age. `status` SHALL distinguish "no heartbeat installed", "installed but
has never ticked", and "installed and ticking", and SHALL flag a heartbeat whose last tick is
older than the interval a healthy backend would tick at, so a dead heartbeat is visible without
inspecting `launchctl` or the crontab.

#### Scenario: Reporting a healthy heartbeat
- **WHEN** a user runs `cronbook status` with a heartbeat installed and ticking
- **THEN** stdout names the installed backend and shows the last tick time and its age

#### Scenario: Reporting a stale heartbeat
- **WHEN** the last tick is older than a healthy backend's tick interval
- **THEN** `status` flags the heartbeat as stale

#### Scenario: Reporting no heartbeat
- **WHEN** a user runs `cronbook status` with no heartbeat installed
- **THEN** `status` reports that no backend is installed

#### Scenario: Reporting a heartbeat that has never ticked
- **WHEN** a heartbeat is installed but no tick has been recorded
- **THEN** `status` reports the backend as installed and the last tick as unknown

#### Scenario: status as JSON
- **WHEN** a user runs `cronbook status --json`
- **THEN** the result object on stdout carries the installed backend, the last tick timestamp, and
  whether the heartbeat is stale

#### Scenario: status changes nothing
- **WHEN** a user runs `cronbook status`
- **THEN** no job, run, log, crontab, or launchd agent is modified

### Requirement: Selecting a job by id or name
Commands that act on a single existing job SHALL identify the target through explicit selector
flags rather than a positional argument. The affected commands are enable, disable, update,
delete, trigger, and kill. `--job-id <id>` selects by the immutable job id, and
`--job-name <name>` selects by the unique job name. At least one selector SHALL be provided; when neither is provided the
command SHALL fail with an error. When both are provided, `--job-id` SHALL take precedence and
`--job-name` SHALL be ignored.

#### Scenario: Selecting by id
- **WHEN** a user runs a single-job command with `--job-id <id>`
- **THEN** the command acts on the job with that id

#### Scenario: Selecting by name
- **WHEN** a user runs a single-job command with `--job-name <name>` and no `--job-id`
- **THEN** the command acts on the job with that name

#### Scenario: Both selectors given
- **WHEN** a user runs a single-job command with both `--job-id` and `--job-name`
- **THEN** the command uses `--job-id` and ignores `--job-name`

#### Scenario: No selector given
- **WHEN** a user runs a single-job command with neither `--job-id` nor `--job-name`
- **THEN** the CLI prints an error and exits with a non-zero status

### Requirement: Selecting a run by id
Commands that act on a single run SHALL identify the target through an explicit `--run-id <id>`
flag rather than a positional argument. The `logs` command SHALL accept `--run-id` to choose
the run whose logs are emitted. When `--run-id` is not provided the command SHALL fail with an
error.

#### Scenario: Selecting a run by id
- **WHEN** a user runs `cronbook logs --run-id <id>`
- **THEN** the command emits the logs of the run with that id

#### Scenario: No run selector given
- **WHEN** a user runs `cronbook logs` with no `--run-id`
- **THEN** the CLI prints an error and exits with a non-zero status

### Requirement: Human-readable output by default
CLI commands that produce structured results SHALL print human-readable output (e.g. tables)
by default.

#### Scenario: Listing jobs interactively
- **WHEN** a user runs `cronbook jobs` without `--json`
- **THEN** the CLI prints a human-readable table of scheduled jobs

### Requirement: Write commands report status on stderr
A command that changes state SHALL, in default (non-JSON) mode, print a human status line to
stderr and place nothing on stdout - keeping stdout free for piping. The state-changing commands
are add, update, delete, enable, disable, trigger, kill, import, install, and uninstall. Under
`--json` the command's result object SHALL instead be emitted on stdout in the `cronbook`
envelope. A read command's data (a table, or raw log bytes) goes to stdout in either mode.

#### Scenario: Write command status on stderr
- **WHEN** a user adds a job without `--json`
- **THEN** stdout is empty and a status line describing the change is written to stderr

#### Scenario: Write command result as JSON on stdout
- **WHEN** a user adds a job with `--json`
- **THEN** the created cronjob object is emitted on stdout in the `cronbook` envelope

### Requirement: Machine-readable JSON output
CLI commands that produce structured results SHALL support a `--json` flag, accepted both before
the subcommand (`cronbook --json <command>`) and after it (`cronbook <command> --json`), that
switches the output to a single JSON object nested
under a top-level `cronbook` key, of the form
`{ "cronbook": { "version": <string>, "data": <object|array>, "error": <null|object> } }`. The
`version` SHALL be a string (e.g. `"1"`). When `--json` is set, errors SHALL be emitted as JSON
on stderr with `error` holding `{ "code": ..., "message": ... }`, and the process exit code
SHALL remain 0 on success and non-zero on error regardless of output format.

#### Scenario: Structured success output
- **WHEN** a user runs `cronbook jobs --json`
- **THEN** stdout contains a JSON object with a top-level `cronbook` key holding a string
  `version`, a `data` array of cronjobs, and `error` set to null
- **AND** the process exits with status 0

#### Scenario: Structured error output
- **WHEN** a user runs a command with `--json` that fails (e.g. an unknown job id)
- **THEN** stderr contains a `cronbook`-wrapped JSON object whose `error` holds a `code` and
  `message`
- **AND** the process exits with a non-zero status

### Requirement: Environment variables are never emitted in JSON
The `env` of a cronjob SHALL NOT be included in any JSON output - neither in `--json` command
output nor in exported files. Environment variables are write-only in the JSON contract: they
may be provided when importing, but cronbook never serializes them back out.

#### Scenario: env absent from jobs output
- **WHEN** a user runs `cronbook jobs --json` for jobs that have environment variables set
- **THEN** the emitted cronjob objects do not contain an `env` field

### Requirement: Raw log content is not wrapped in JSON
The command that outputs a run's log content SHALL emit the raw log bytes by default. When
`--json` is supplied to that command, it SHALL return only run metadata (path, size, exit
code, timing) and SHALL NOT embed the log content as a JSON string.

#### Scenario: Outputting raw logs
- **WHEN** a user outputs the logs of a run without `--json`
- **THEN** the CLI writes the run's raw stdout/stderr bytes unmodified

#### Scenario: Log metadata as JSON
- **WHEN** a user outputs the logs of a run with `--json`
- **THEN** the CLI returns a JSON envelope containing metadata only and not the log content
