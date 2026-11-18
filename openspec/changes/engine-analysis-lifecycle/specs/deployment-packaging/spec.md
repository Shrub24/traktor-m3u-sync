## ADDED Requirements

### Requirement: Engine guest task package
The flake SHALL expose `packages.engine-analysis-guest` containing a Windows script that
registers an interactive logon task which starts Engine DJ on a file request and requests a
normal close on a second file request. The task SHALL answer Engine's prompts through Windows UI
Automation.

#### Scenario: Normal close only
- **WHEN** Engine does not exit within the close timeout
- **THEN** the task reports failure and does not force-terminate Engine

#### Scenario: Engine already running
- **WHEN** Engine is already running at request time
- **THEN** the task reports failure without closing it

#### Scenario: Known prompts
- **WHEN** Engine shows the quit confirmation or one of the listed notices (unsupported drive format, mono audio output)
- **THEN** the task answers YES or OK by the control's accessible name

#### Scenario: Unknown dialog
- **WHEN** Engine shows any other dialog
- **THEN** the task leaves it open and reports failure with the dialog's text
