## ADDED Requirements

### Requirement: Engine analysis status
The `engine-analysis` command SHALL report, read-only, whether analysis is saved for each
local track in the managed Engine playlist subtree.

#### Scenario: Saved analysis requires a persisted beat grid
- **WHEN** a managed track has `isAnalyzed` set but no saved beat grid, or is not analyzed
- **THEN** it is reported as not saved, and as saved once both are present

#### Scenario: Only the managed subtree counts
- **WHEN** tracks appear only in unmanaged playlists or reference another Engine database
- **THEN** they are not reported

#### Scenario: Locked database
- **WHEN** another process holds the database locked beyond the timeout
- **THEN** the command exits 75 with `code=engine_busy` and does not modify the database

#### Scenario: Unsupported database
- **WHEN** the schema is not 3.0.2 or the managed root is absent or duplicated
- **THEN** the command exits 1 with `code=engine_analysis_failed`
