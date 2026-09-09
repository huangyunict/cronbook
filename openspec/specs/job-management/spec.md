# job-management Specification

## Purpose

Defines the job data model and the lifecycle operations for managing jobs: add,
update, delete, enable/disable, and list.

## Requirements

### Requirement: Job definition
A job SHALL be defined by: an immutable system-generated id (a UUID rendered in its canonical
dashed form, e.g. `020981c2-0773-463f-9bca-ffb4bfc3152b`), a unique name, an
optional free-text description, a cron schedule expression, a command (run via the shell,
`/bin/sh -c`), a required working directory, environment variables, a timeout (defaulting to
unlimited/no timeout), an optional timezone (defaulting to local time), and an enabled flag. There
is no overlap-policy field; overlapping runs of the same job are always skipped. The working
directory MAY contain `~` and `$VAR` / `${VAR}` references, which SHALL be expanded when the job
runs; the stored definition SHALL retain the value as written. Job definitions and their schedules
SHALL be stored in the repository database, which is the source of truth for job configuration. A
job MAY be referenced on the command line by either its id or its unique name.

#### Scenario: Stored fields are retrievable
- **WHEN** a job is added with a name, description, schedule, command, working directory, and
  environment
- **THEN** listing or inspecting that job returns all of those fields as stored, including a
  system-generated UUID id

#### Scenario: Working directory is required
- **WHEN** a user adds a job without providing a working directory
- **THEN** the CLI rejects the request with an error

#### Scenario: Referencing a job by name
- **WHEN** a user runs a command targeting a job by its unique name
- **THEN** the command operates on the job with that name

### Requirement: Add a job
The CLI SHALL add a new job from the command line, persisting it to the repository. The job's id
SHALL be a system-generated UUID, rendered in its canonical dashed form, assigned at creation time. The job's name SHALL be unique
across all jobs; adding a job with a name that already exists SHALL be rejected.

#### Scenario: Adding a job
- **WHEN** a user runs the add command with a unique name, a valid schedule, and a command
- **THEN** a new job is persisted with a system-generated UUID id and is included in the
  scheduled-jobs list

#### Scenario: Rejecting a duplicate name
- **WHEN** a user attempts to add a job whose name already exists
- **THEN** the CLI rejects the request with an error and does not persist the job

#### Scenario: Rejecting an invalid schedule
- **WHEN** a user attempts to add a job with an invalid cron expression
- **THEN** the CLI rejects the request with an error and does not persist the job

#### Scenario: Rejecting a working directory that does not exist
- **WHEN** a user attempts to add a job whose working directory (after `~`/`$VAR` expansion)
  is not an existing directory
- **THEN** the CLI rejects the request with an error and does not persist the job

### Requirement: Update a job
The CLI SHALL update an existing job identified by its id or name. The job id SHALL NOT be
modifiable. The job name MAY be updated, but the new name MUST remain unique; an update to a
name that collides with another job SHALL be rejected. An update SHALL change only the stored
definition; it SHALL NOT rewrite the crontab and SHALL NOT affect any in-flight run of that
job.

#### Scenario: Updating a job's schedule
- **WHEN** a user updates an existing job's schedule
- **THEN** the stored schedule changes and takes effect on the next dispatcher tick

#### Scenario: Renaming a job to a free name
- **WHEN** a user updates a job's name to one not used by any other job
- **THEN** the job's name is changed and its id is unchanged

#### Scenario: Rejecting a rename collision
- **WHEN** a user updates a job's name to one already used by another job
- **THEN** the CLI rejects the request and the name is unchanged

#### Scenario: Attempting to change the id
- **WHEN** a user attempts to modify a job's id
- **THEN** the CLI rejects the request

#### Scenario: Update does not disturb a running instance
- **WHEN** a user updates a job that currently has a run in flight
- **THEN** the in-flight run continues unaffected

#### Scenario: Rejecting a working directory that does not exist
- **WHEN** a user updates a job's working directory to a path that (after `~`/`$VAR` expansion)
  is not an existing directory
- **THEN** the CLI rejects the request with an error and the stored working directory is unchanged

### Requirement: Delete a job
The CLI SHALL delete a job identified by its id or name. Deleting a job SHALL remove the job
definition and its run history (the run rows) from the repository; run history is not preserved.
Two independent behaviors govern the delete and MAY be combined:

- **In-flight handling.** By default the delete SHALL wait for any in-flight run of the job to
  finish before removing it. A `--force` flag SHALL instead kill the in-flight run using the same
  mechanism as the `kill` command - cooperatively when the run's worker is alive (marking it
  `killed` so the worker terminates its own process group on its next heartbeat), or by directly
  terminating the recorded process group when the worker is not alive - and SHALL wait until that
  run is no longer in flight (its lease has cleared or expired, or the run reached a terminal
  status) before removing the job, so that "the job is gone" means its process is gone. This wait
  is bounded by the lease TTL. When the kill is cooperative, `--force` SHALL inform the user that
  termination was requested and may take up to roughly one heartbeat interval plus the grace
  period.
- **Log disposal.** By default the job's log files SHALL be moved to a trash area (trash is not
  auto-expired in v1; automatic cleanup is deferred to `gc` in a later milestone); a `--purge`
  flag SHALL permanently delete the log files immediately, skipping the trash area.

#### Scenario: Deleting an idle job
- **WHEN** a user deletes a job that is not running
- **THEN** the job and its run history are removed and its log files are moved to the trash area

#### Scenario: Deleting a running job by default
- **WHEN** a user deletes a job that has a run in flight without any flag
- **THEN** cronbook waits for the in-flight run to finish before removing the job

#### Scenario: Force-deleting a running job
- **WHEN** a user deletes a running job with `--force`
- **THEN** the in-flight run is killed (cooperatively if its worker is alive, else by directly
  terminating its process group), cronbook waits until the run is no longer in flight, and then
  the job is removed

#### Scenario: Purging on delete
- **WHEN** a user deletes a job with `--purge`
- **THEN** the job's log files are permanently deleted immediately instead of being moved to
  trash

### Requirement: Enable and disable a job
Enabling or disabling a job SHALL be a change to the job's enabled flag in the repository only,
and SHALL NOT edit the crontab. Only enabled jobs SHALL be considered for dispatch.

#### Scenario: Disabling a job
- **WHEN** a user disables a job
- **THEN** the job's enabled flag is cleared and the dispatcher no longer runs it on schedule

### Requirement: List scheduled jobs
The CLI SHALL list scheduled jobs via the `jobs` command, showing each job's cron job id and
other relevant information from the stored definition.

#### Scenario: Listing scheduled jobs
- **WHEN** a user runs `cronbook jobs`
- **THEN** the output includes each job's id and its schedule and other stored details
