# import-export Specification

## Purpose

Defines how cronjob definitions are exported to and imported from JSON,
including the document contract, validation, merge modes, and round-trip
fidelity.

## Requirements

### Requirement: Export cronjob config to JSON
The CLI SHALL export cronjob definitions from the repository to a JSON file. The document SHALL
be a single top-level `cronbook` object containing a string `version` (e.g. `"1"`), an
informational `exported_at` UTC timestamp, and a `cronjobs` array. Each element SHALL be a
cronjob object using the same shape as the `--json` output. Export SHALL include cronjob
definitions only - never run history or logs - and SHALL NOT include the jobs' environment
variables. Setting file permissions on the exported file is left to the user.

#### Scenario: Exporting cronjobs
- **WHEN** a user exports cronjob config to a JSON file
- **THEN** the file has a top-level `cronbook` object with a string `version` and a `cronjobs`
  array of definitions

#### Scenario: Environment variables are excluded from export
- **WHEN** a user exports cronjobs that have environment variables set
- **THEN** the exported cronjob objects contain no `env` field

### Requirement: Import validates before applying
The CLI SHALL import cronjob configuration from a JSON file into the repository. The file MUST
have a top-level `cronbook` object whose `version` string exactly matches the version supported
by this cronbook; any other value SHALL be rejected. The import SHALL validate the document and
each cronjob entry (including required fields `name`, `schedule`, `command`, `working_dir`, and
`enabled`, and the optional `hosts` field, which when present MUST be a list of strings) and
SHALL reject malformed or unsupported input in its entirety, without applying any entry. There
is no overlap field: overlap is always skip.

#### Scenario: Rejecting an unsupported version
- **WHEN** a user imports a file whose `cronbook.version` does not exactly match the supported
  version
- **THEN** the import is rejected with an error and no jobs are added or changed

#### Scenario: Rejecting malformed input
- **WHEN** a user imports a file that is malformed or missing required cronjob fields
- **THEN** the import is rejected with an error and no jobs are added or changed

#### Scenario: Rejecting a malformed host filter
- **WHEN** a user imports a file where an entry's `hosts` field is present but is not a list of strings
- **THEN** the import is rejected with an error and no jobs are added or changed

### Requirement: Per-host import filtering
Import SHALL honor an optional per-entry `hosts` field - a list of hostname
strings the entry applies to - that restricts which machines apply that entry.
On import, when an entry's
`hosts` list is present and non-empty, the entry SHALL be applied only if the
importing machine's hostname matches one of the listed hosts; a match SHALL be
recognized only when the machine's hostname equals a listed value verbatim.
Both the config and the resolved hostname use the full hostname form; no
short-form (pre-`.` segment) comparison is performed. When the machine's
hostname matches no listed host, the entry SHALL be
skipped with a host-mismatch reason and no job SHALL be inserted, replaced, or
otherwise changed for it, while the remaining entries continue to be processed.
When the `hosts` field is absent or is an empty list, the entry SHALL apply to
any host (unfiltered), preserving today's behavior. The `hosts` field is
import-only metadata: it SHALL NOT be stored on the job and SHALL NOT be emitted
by export or `--json` output.

#### Scenario: Entry applied on a matching host
- **WHEN** an entry lists `hosts` that includes the importing machine's full hostname
- **THEN** the entry is processed under the normal merge rules (inserted or replaced)

#### Scenario: Short-form hostname does not match
- **WHEN** the machine reports a full hostname (e.g. `foo.example.com`) but the entry's `hosts` lists only its short form (e.g. `foo`)
- **THEN** the entry is skipped with a host-mismatch reason and no job is inserted, replaced, or changed for it

#### Scenario: Entry skipped on a non-matching host
- **WHEN** an entry lists a non-empty `hosts` that does not include the importing machine's hostname
- **THEN** the entry is skipped with a host-mismatch reason and no job is inserted, replaced, or changed for it, while other entries continue to be processed

#### Scenario: Entry with no host filter applies everywhere
- **WHEN** an entry has no `hosts` field, or `hosts` is an empty list
- **THEN** the entry applies on any host and is processed under the normal merge rules

#### Scenario: Host filter is not persisted or exported
- **WHEN** an entry carrying a `hosts` field is imported and applied
- **THEN** the stored job records no host filter and a subsequent export or `--json` output contains no `hosts` field

### Requirement: Default import merge (insert-or-replace)
By default, import SHALL merge each JSON entry into the repository as insert-or-replace, matching
against existing jobs by id and by name. For each entry: when neither its id nor its name
matches any existing job, the entry SHALL be inserted; when its id and its name both match the
same existing job, that job SHALL be replaced. When only the id matches, only the name matches,
or the id and name match different existing jobs, that entry SHALL fail with a warning while
the remaining entries continue to be merged. Existing jobs not listed in the JSON SHALL NOT be
modified or removed.

#### Scenario: Inserting a new entry
- **WHEN** an imported entry has an id and name that match no existing job
- **THEN** the entry is inserted as a new job

#### Scenario: Replacing an exact match
- **WHEN** an imported entry's id and name both match the same existing job
- **THEN** that job is replaced with the imported definition

#### Scenario: Partial-match conflict is skipped with a warning
- **WHEN** an imported entry matches an existing job by only its id, only its name, or matches
  different jobs by id and name
- **THEN** that entry fails with a warning and no change is made for it, while other
  non-conflicting entries are still merged

#### Scenario: Unlisted jobs are untouched
- **WHEN** the repository contains jobs that are not present in the imported JSON
- **THEN** those jobs are left unchanged

### Requirement: Insert-only import mode
When invoked with `--insert-only`, import SHALL insert only entries whose id and name match no
existing job, and SHALL report a per-entry error for any entry whose id or name conflicts with
an existing job. Existing jobs not listed in the JSON SHALL NOT be modified or removed.

#### Scenario: Insert-only with a conflict
- **WHEN** a user imports with `--insert-only` and one entry's id or name already exists
- **THEN** that entry is reported as an error and not applied, while new entries are inserted

### Requirement: Round-trip fidelity
Configuration exported to JSON and then imported SHALL reproduce the same cronjob definitions,
except environment variables, which are not exported and therefore not restored.

#### Scenario: Export then import
- **WHEN** a user exports cronjob config and then imports the same file into an empty repository
- **THEN** the resulting cronjob definitions match the originals except that environment
  variables are absent
