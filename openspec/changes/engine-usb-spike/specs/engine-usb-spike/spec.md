## ADDED Requirements

### Requirement: Stage a native Engine USB library

The spike SHALL read an offline Engine 3.0.2 media library and populate a new directory with all selected playlist trees and the tracks those trees reference, including audio, available linked artwork and persisted analysis. It SHALL preserve playlist order and source track origin, assign a separate device database UUID, and leave the source unchanged.

#### Scenario: Generate a fresh export

- **WHEN** the operator stages the library after an Engine sync and analysis run
- **THEN** the output reflects the current playlists, tracks and saved analysis without reusing the older USB database

#### Scenario: An asset is missing

- **WHEN** a required track, analysis file or linked thumbnail is missing
- **THEN** the spike fails without publishing the incomplete tree
