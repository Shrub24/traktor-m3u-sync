## ADDED Requirements

### Requirement: Allow downstream service arguments
The NixOS module SHALL expose explicit import and export service argument options so downstream policy can opt into supported CLI operational flags without replacing the generated service command.

#### Scenario: Export service uses extra arguments
- **WHEN** an operator configures export service extra arguments including `--fail-on-warning`
- **THEN** the generated export oneshot appends those arguments after its explicit format and config arguments
- **AND** the module preserves its separate import/export service boundary

#### Scenario: Service arguments preserve external config paths
- **WHEN** an operator configures an external config file path containing spaces or percent characters with service extra arguments
- **THEN** the generated import or export command preserves that path as one config argument
- **AND** appends each extra argument without altering command argument boundaries
