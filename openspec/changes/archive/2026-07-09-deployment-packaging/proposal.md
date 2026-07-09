## Why

The repository now has working export and import workflows, but it is still only developer-runnable through the dev shell rather than deployable as a reusable Nix-native application. The next change is needed now to produce a real runtime artifact and a generic declarative integration surface without pulling homelab-specific orchestration into this repo.

## What Changes

- Add a real flake package for the `traktor-m3u-sync` CLI as the canonical runtime artifact.
- Add a flake app for `nix run` convenience while keeping the package as the primary deployment primitive.
- Add a generic NixOS module that exposes separate declarative `export` and `import` oneshot services rather than a combined sync abstraction.
- Add declarative configuration generation that renders module-provided Nix settings into the TOML format already used by the CLI.
- Add deployment-oriented documentation and examples showing how downstream systems can attach timers, ordering, and other orchestration policies without hard-coding them into this repo.

## Capabilities

### New Capabilities
- `deployment-packaging`: Provide a Nix-native runtime package, flake app, declarative service/module integration, and configuration-rendering support for deploying the sync worker.

### Modified Capabilities
- `developer-workspace`: Expand the workspace contract so the repository exposes canonical buildable runtime artifacts in addition to local development tooling.

## Impact

- Extends `flake.nix` with runtime outputs beyond the current dev shell and formatter/check wiring.
- Likely adds Nix packaging helpers and one or more NixOS module files.
- May require Nix-side handling for Python runtime dependencies such as `traktor-nml-utils`.
- Adds deployment documentation and example configuration patterns while intentionally leaving host-specific timers, path units, and Syncthing wiring to downstream repos.
