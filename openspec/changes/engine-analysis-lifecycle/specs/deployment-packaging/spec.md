## ADDED Requirements

### Requirement: Engine guest task package
The flake SHALL expose `packages.engine-analysis-guest` containing a Windows script that
registers an interactive logon task which starts Engine DJ on a file request and requests a
normal close on a second file request.

#### Scenario: Normal close only
- **WHEN** Engine does not exit within the close timeout
- **THEN** the task reports failure and does not force-terminate Engine

#### Scenario: Engine already running
- **WHEN** Engine is already running at request time
- **THEN** the task reports failure without closing it
