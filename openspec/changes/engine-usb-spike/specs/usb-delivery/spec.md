## ADDED Requirements

### Requirement: Deliver a staged USB generation over SFTP

The manual delivery command SHALL select a stick by an operator-provisioned marker. It SHALL compare content manifests independently of timestamps, use a pinned SSH host key, and publish the activation file only after all required assets are present. It SHALL back up the current activation file before replacing it. It SHALL NOT delete media, replace assets referenced by the active generation, or overwrite an unrecognized database.

#### Scenario: Deliver a library update
- **WHEN** the stick has a previously installed generation and the new export adds media
- **THEN** unchanged media is not transferred, new assets arrive first, and the verified database is published last

#### Scenario: A transfer is interrupted
- **WHEN** delivery fails before publication
- **THEN** the old database and the assets it references remain in place
- **AND** retrying can recognize assets completed during the interrupted attempt

#### Scenario: Player edits exist
- **WHEN** the database does not match a recorded delivery for that stick
- **THEN** delivery retains a local copy and stops without replacing the database
