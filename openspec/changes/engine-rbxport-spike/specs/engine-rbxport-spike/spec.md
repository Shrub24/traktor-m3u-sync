## ADDED Requirements

### Requirement: Build a trial Pioneer USB tree from Engine analysis
The spike SHALL use an Engine 3.0.2 snapshot as a read-only source of timing and key. It SHALL derive waveforms from the source audio and SHALL NOT independently detect tempo or key. It SHALL write to a new output directory.

#### Scenario: Selected analyzed tracks
- **WHEN** the operator supplies analyzed Engine track IDs in playlist order and the source audio is available
- **THEN** the spike writes a Pioneer USB tree with those tracks in the specified order and with the supplied grid, key and supported cue/loop positions

#### Scenario: Existing destination
- **WHEN** the output directory already exists
- **THEN** the spike refuses to export rather than overwriting it

### Requirement: Rehearse Engine's interactive lifecycle
The Windows pilot SHALL run in the signed-in DJ user's desktop session. It SHALL request a normal window close only for the Engine process it launched and only after operator confirmation. It SHALL NOT report analysis completion or shut down the VM.

#### Scenario: Engine already running
- **WHEN** the pilot is started while Engine is already open
- **THEN** it fails without closing the existing Engine process

#### Scenario: Operator confirms close
- **WHEN** the operator confirms that Engine should close
- **THEN** the pilot requests a normal close and reports success only if the launched process exits with status zero within the close timeout
