## ADDED Requirements

### Requirement: Support explicit operational command controls
The system SHALL expose explicit command flags for operational behavior without changing the default import/export result contract.

#### Scenario: Operational flags are explicit
- **WHEN** an operator invokes an import or export command without operational flags
- **THEN** the command retains its existing result and exit behavior

#### Scenario: Warning-sensitive automation
- **WHEN** an operator invokes a command with `--fail-on-warning`
- **THEN** the command exposes warning completion through its documented distinct status
