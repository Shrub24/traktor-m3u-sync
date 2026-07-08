## Purpose

Provide canonical repository documentation that defines architecture direction, conventions, and ongoing documentation maintenance expectations.

## Requirements

### Requirement: Repository root documents project direction
The repository SHALL include canonical root-level documents that describe project architecture direction, near-term plan, and repository conventions.

#### Scenario: New contributor looks for project guidance
- **WHEN** a contributor opens the repository root
- **THEN** they can find documents that explain the architecture direction, current plan, and repository conventions without reading implementation code or private chat history

### Requirement: Agent guidance indexes canonical docs
The repository SHALL provide an `AGENTS.md` document that acts as a high-level directive and index for canonical repo guidance.

#### Scenario: Agent needs authoritative guidance
- **WHEN** an agent begins work in the repository
- **THEN** `AGENTS.md` directs it to the relevant convention, architecture, planning, and style documents and identifies them as canonical references

### Requirement: Documentation maintenance is explicit
The repository SHALL document that project conventions and guidance files must be updated when implementation decisions materially change them.

#### Scenario: Conventions change during implementation
- **WHEN** a change introduces or revises important repo conventions, workflow expectations, or architecture guidance
- **THEN** the relevant root documentation is updated as part of that change instead of being deferred indefinitely
