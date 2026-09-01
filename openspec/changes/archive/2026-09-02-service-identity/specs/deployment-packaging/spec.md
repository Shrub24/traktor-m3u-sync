## ADDED Requirements

### Requirement: Run services under a dedicated non-root identity
The NixOS module SHALL run the import and export oneshot services under a configurable user and group whose default is a dedicated `playlist-sync` system account that the module creates automatically.

#### Scenario: Default service identity
- **WHEN** a NixOS configuration enables either traktor-m3u-sync service without setting `user` or `group`
- **THEN** the module declares a `playlist-sync` system user and group with no login shell
- **AND** both generated units set `User=` and `Group=` to that account

#### Scenario: Operator-managed identity override
- **WHEN** an operator points both `user` and `group` at a non-default account
- **THEN** the generated units run as that identity
- **AND** the module does not create a conflicting account

#### Scenario: Shared media group access
- **WHEN** an operator configures one or more supplementary groups
- **THEN** both generated units add those groups through `SupplementaryGroups=`
- **AND** the module does not hard-code a site-specific group

#### Scenario: Generated config uses a writable explicit store
- **WHEN** the generated module config runs under a non-root identity
- **THEN** evaluation requires an explicit `store.path`
- **AND** the service does not fall back to a home-relative path under `/var/empty`

#### Scenario: Explicit root escape hatch
- **WHEN** an operator sets `user = null`
- **THEN** the module does not create the dedicated account or group
- **AND** the generated units omit `User=` and `Group=`
