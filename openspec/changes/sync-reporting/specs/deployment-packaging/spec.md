## MODIFIED Requirements

### Requirement: Generate isolated systemd jobs with validated success fan-out
The system SHALL generate one declared template-instance drop-in per job with its effective config, format, arguments, stable unit name, and validated `OnSuccess=` fan-out, and SHALL support a symmetric per-job `onFailure` list rendered as systemd `OnFailure=` for downstream notify/cleanup units. Timers, path units, restart policy, and consumer ordering remain downstream policy.

#### Scenario: Success fan-out preserved
- **WHEN** a job lists `onSuccess` targets
- **THEN** the instance wires validated `OnSuccess=` exactly as before

#### Scenario: Failure fan-out triggers
- **WHEN** a job lists `onFailure` targets and the instance fails
- **THEN** systemd activates the listed units
- **AND** invalid references fail at Nix evaluation like `onSuccess`

## ADDED Requirements

### Requirement: Render per-job report file arguments
The system SHALL render a per-job `reportFile` as a distinct escaped `--report-file <path>` argv pair in the job's ExecStart when set, and SHALL omit the argument entirely when unset.

#### Scenario: Spaced report path stays one argv
- **WHEN** a job sets `reportFile` to a path containing spaces
- **THEN** the generated ExecStart carries a single escaped `--report-file` argument pair
- **AND** jobs without `reportFile` gain no extra arguments
