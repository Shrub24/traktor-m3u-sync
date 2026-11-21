## ADDED Requirements

### Requirement: Refresh DJ exports
A refresh SHALL update playlists and Engine, complete any required Engine analysis, then build the requested formats from the closed library without writing to a stick.

#### Scenario: Playlist-only refresh
- **WHEN** playlists changed but all selected tracks have saved analysis
- **THEN** refresh skips guest analysis and still builds the requested formats

#### Scenario: Analysis does not complete
- **WHEN** required analysis fails or Engine cannot be confirmed closed
- **THEN** refresh does not build from that library and reports why it stopped

### Requirement: Guide per-stick delivery
Stick sync SHALL require an explicit target, offer Engine edit review before replacement, and preview the transfer before asking for delivery approval. It SHALL retain existing library safety checks.

#### Scenario: Keep player edits
- **WHEN** the operator approves eligible edits
- **THEN** the edits are applied and affected exports are rebuilt before delivery is previewed

#### Scenario: Decline delivery
- **WHEN** the operator declines the transfer plan
- **THEN** sync does not write to the stick

#### Scenario: Stick changed after preview
- **WHEN** the stick or its database no longer matches the approved operation
- **THEN** sync refuses replacement and requests a new review or delivery decision as appropriate

### Requirement: Report workflow outcomes
Each workflow SHALL expose a versioned run report and show its current stage and measured progress. Its final status SHALL distinguish success, partial success and failure, with a reason and next action for any failed stage.

#### Scenario: One format fails
- **WHEN** Engine publishes and Pioneer build fails
- **THEN** the report identifies the new Engine generation, the Pioneer failure, and any previous Pioneer generation still usable
- **AND** it does not report overall success

### Requirement: Retry only affected work
Retry SHALL reuse successful outputs and completed transfers when their inputs still match and existing safety checks pass.

#### Scenario: Connection lost in delivery
- **WHEN** the operator retries an interrupted transfer to the same stick and generation
- **THEN** delivery rechecks its publication guards and resumes without rerunning playlist fetch or Engine analysis
