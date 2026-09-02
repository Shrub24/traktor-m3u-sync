## 1. Module Model

- [x] 1.1 Replace singleton workflow options with typed `states.<name>` and `jobs.<name>` submodules, preserving package and shared identity controls; verify representative state/job configurations evaluate and legacy singleton options are absent
- [x] 1.2 Add boundary assertions for valid job names, existing state and success references, one import per state, distinct state stores, action-compatible formats, matched custom identity names, and acyclic success graphs; verify invalid configurations fail with module-owned messages

## 2. Job Configuration

- [x] 2.1 Render one effective TOML file per generated job from its referenced state and selected format settings, or use its external `configFile`; verify every supported import/export format loads through the packaged CLI config loader
- [x] 2.2 Build each job's escaped CLI argument vector from package, action, format, config path, and `extraArgs`; verify paths containing spaces/percent characters and `--dry-run`/`--fail-on-warning` remain distinct arguments

## 3. systemd Instances

- [x] 3.1 Define shared import and export oneshot template units with the existing `playlist-sync` identity, supplementary groups, and no implicit triggers; verify template unit files contain the common command and service policy exactly once
- [x] 3.2 Generate one declared template-instance drop-in per job with its effective config, format, arguments, stable unit name, and validated `OnSuccess=` fan-out; verify import-only, export-only, linear-chain, and one-to-many fan-out fixtures produce the expected units

## 4. Migration And Documentation

- [x] 4.1 Update `docs/nix-deployment.md` with the complete states/jobs option reference, singleton migration example, direct `systemctl` usage, success/failure semantics, and downstream timer/path/consumer-trigger examples; verify examples match generated unit names
- [x] 4.2 Update `ARCHITECTURE.md` and `PLAN.md` to replace singleton service topology with named state/action jobs while retaining the downstream-policy and Engine-offline boundaries; verify no canonical document describes the removed singleton contract as current

## 5. Validation

- [x] 5.1 Update the minimal flake module-evaluation check for one state, one import, iTunes and Engine export fan-out, shared identity, and packaged config loading; verify `nix flake check` passes
- [x] 5.2 Run `just check`, build the runtime package, run `openspec validate nix-job-orchestration --type change --strict`, and complete a focused Nix/systemd review with no unresolved high-severity findings
