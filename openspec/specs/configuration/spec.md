# configuration Specification

## Purpose

Defines how cronbook locates and loads its TOML configuration and the settings
(with defaults) that all cronbook entry points share.

## Requirements

### Requirement: TOML config file with defined resolution order
cronbook SHALL read its configuration from a TOML file whose location is resolved in order:
the `--config-toml <path>` flag, then the default `~/.config/cronbook/config.toml`. All cronbook
entry points SHALL resolve configuration the same way so the CLI, the dispatcher, and workers
agree on settings. A missing config file SHALL NOT be an error; it yields an all-defaults
configuration.

#### Scenario: Explicit flag wins
- **WHEN** `--config-toml <path>` is provided
- **THEN** cronbook loads configuration from that path

#### Scenario: Default path
- **WHEN** `--config-toml` is not provided
- **THEN** cronbook loads configuration from `~/.config/cronbook/config.toml`

#### Scenario: Missing file uses defaults
- **WHEN** the resolved config file does not exist
- **THEN** cronbook uses an all-defaults configuration

### Requirement: Configurable settings with defaults
The config file SHALL hold the storage paths (`db_path`, `app_log_dir`, `internal_log_dir`,
`trash_dir`), run settings (`max_head_log_lines`, `max_tail_log_lines`, `max_concurrent_runs`),
and retention settings (`keep_last_runs`, `trash_retention_days`).
`app_log_dir` holds per-run job stdout/stderr; `internal_log_dir` is dedicated to cronbook's own
operational logs (e.g. dispatcher errors) and is separate from `app_log_dir`; `trash_dir` is
where a deleted job's log files are moved (unless purged). Each setting
SHALL have a sensible default when absent: `db_path` = `~/.cronbook/cronbook.db`, `app_log_dir` =
`~/.cronbook/logs`, `internal_log_dir` = `~/.cronbook/internal-logs`, `trash_dir` =
`~/.cronbook/trash`, `max_head_log_lines` = 1000,
`max_tail_log_lines` = 10000, and `max_concurrent_runs` = 100. The retention settings
`keep_last_runs` (maximum runs retained per job) and `trash_retention_days` (maximum age of trashed
deleted-job logs, in days) live in a `[retention]` section; each SHALL be a positive integer
and SHALL default when absent to `keep_last_runs` = 10 and `trash_retention_days` = 7.
There is no overlap-policy
setting: overlap is always "skip if a run is in flight". The run lease TTL and the worker
heartbeat interval are fixed internal constants (not configurable). The `trash_dir` location is
part of the config, and its automatic expiry is governed by `trash_retention_days` via `prune`.
Dashboard bind settings (`host`, `port`) are introduced with the web dashboard in a later
milestone and are not part of this config.

#### Scenario: Missing values use defaults
- **WHEN** the config file omits a setting
- **THEN** cronbook uses that setting's documented default

#### Scenario: Overridden path is honored everywhere
- **WHEN** `db_path` is set to a custom path in the config
- **THEN** the CLI, dispatcher, and workers all use that database path

#### Scenario: Retention settings use defaults when omitted
- **WHEN** the config omits `keep_last_runs` and `trash_retention_days`
- **THEN** `keep_last_runs` defaults to 10 and `trash_retention_days` defaults to 7

#### Scenario: Rejecting a non-positive retention value
- **WHEN** `keep_last_runs` or `trash_retention_days` is set to a non-integer or a value less than 1
- **THEN** cronbook reports a configuration error
