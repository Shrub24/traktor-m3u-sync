## Context

`traktor-m3u-sync` now has working batch-oriented `export` and `import` CLI workflows, but its flake still only exposes a developer shell, formatter, and formatting check. The project needs a deployable runtime artifact and a generic declarative integration surface that remain Nix-native while keeping host-specific scheduling and orchestration outside this repo.

This change sits at the boundary between application packaging and operations. It must add enough Nix-native structure to make the tool installable and declaratively runnable, while avoiding premature coupling to timers, path units, Syncthing hooks, or a homelab-specific service topology.

## Goals / Non-Goals

**Goals:**
- Provide a real flake package for the CLI as the canonical runtime artifact.
- Provide a flake app for `nix run` convenience.
- Keep the development shell separate from the runtime closure.
- Add a generic NixOS module with explicit `export` and `import` oneshot service surfaces.
- Keep TOML as the CLI contract while allowing Nix to render TOML configuration declaratively.
- Document the boundary between repo-provided deployment primitives and downstream orchestration policy.

**Non-Goals:**
- Add timers, path units, Syncthing-specific hooks, or host-specific orchestration policy.
- Introduce a combined `sync` command or service abstraction.
- Add callback, retry, or scheduling logic to the CLI itself.
- Solve multi-instance jobs abstraction in this change.
- Finalize non-Nix distribution paths such as PyPI or Homebrew.

## Decisions

### 1. Use a real flake package as the primary runtime artifact
- **Decision:** Add `packages.<system>.default` (and named package output) as the primary deployable artifact, with `apps.<system>.default` layered on top for `nix run` convenience.
- **Rationale:** Services and downstream systems should depend on a stable package, not a dev shell. Apps improve ergonomics but should remain a thin wrapper around the package.
- **Alternatives considered:**
  - Shell-wrapping `uv run`: rejected because it is not the canonical runtime artifact.
  - App-only output: rejected because modules and system packages should depend on packages, not app wrappers.

### 2. Keep dev and runtime environments separate
- **Decision:** Continue using the existing dev shell for development tooling, but build a smaller runtime package that contains only the application and its runtime dependencies.
- **Rationale:** This preserves a clean operational boundary and avoids leaking development tools into deployment closures.
- **Alternatives considered:**
  - Reusing the dev shell for runtime execution: rejected because it blurs responsibilities and increases runtime closure size unnecessarily.

### 3. Prefer Nix-native Python application packaging
- **Decision:** Package the CLI through a Nix-native Python application path rather than a dev-shell wrapper. The exact implementation should preserve the project’s Python metadata and runtime dependencies, including `traktor-nml-utils`.
- **Rationale:** The runtime package must be reproducible, installable, and compatible with Nix module usage.
- **Alternatives considered:**
  - Pure wrapper around the existing local environment: rejected as a non-canonical deployment model.
  - Non-Nix-first packaging as the main path: rejected because Nix-native packaging is the current priority.

### 4. Expose explicit export/import service surfaces instead of a generic job abstraction
- **Decision:** The module will expose distinct `export` and `import` oneshot service surfaces rather than a `jobs.<name>` abstraction.
- **Rationale:** `export` and `import` have different operational semantics and safety profiles. The explicit model is easier to understand and document at this stage.
- **Alternatives considered:**
  - Generic `jobs` submodule: deferred because it adds abstraction overhead before multi-instance use is a first-class need.
  - Single `sync` surface: rejected because it hides important control boundaries.

### 5. Keep TOML as the runtime contract and let Nix render it
- **Decision:** Nix module configuration will render TOML consumed by the existing CLI `--config` path rather than bypassing the app’s config model.
- **Rationale:** This preserves one application-facing contract across Nix and non-Nix environments and avoids introducing a second config interface.
- **Alternatives considered:**
  - Separate Nix-only config plumbing passed as many CLI flags: rejected because it duplicates config semantics.
  - Nix replacing TOML entirely: rejected because the CLI should remain portable.

### 6. Leave orchestration policy downstream
- **Decision:** Provide module and documentation seams for timers/orderings, but do not ship timers, path units, Syncthing integration, or host-specific policies in this change.
- **Rationale:** These choices are environment-specific and belong in downstream infrastructure repos or later focused changes.
- **Alternatives considered:**
  - Bundling timers now: rejected as unnecessary policy baked into a generic tool repo.

## Risks / Trade-offs

- **[Nix packaging complexity around Python dependencies]** → Mitigation: keep the scope focused on a single package/app path and explicitly account for `traktor-nml-utils` in the packaging design.
- **[Module surface may feel slightly opinionated]** → Mitigation: expose package and config override seams so downstream users can adapt without forking the module.
- **[Explicit export/import services may limit future multi-instance ergonomics]** → Mitigation: keep the design evolvable toward a future jobs abstraction if real multi-instance demand emerges.
- **[No timers shipped may disappoint users expecting turnkey automation]** → Mitigation: provide docs/examples for downstream timer attachment while keeping policy out of this repo.
- **[Operational confidence without real homelab wiring is partial]** → Mitigation: treat this change as packaging and declarative interface work, not full deployment validation.

## Migration Plan

1. Extend the flake with package and app outputs.
2. Add any Nix-side packaging helpers needed for runtime dependencies.
3. Add a NixOS module with explicit export/import oneshot service definitions.
4. Render TOML config from declarative module settings and wire services to `--config`.
5. Add docs and examples describing package usage and downstream orchestration attachment.
6. Validate package, app, and module surfaces with targeted Nix checks.

Rollback is straightforward: revert the new packaging/module files and flake outputs if the runtime packaging shape proves unsuitable.

## Open Questions

- Whether phase-3 docs should also introduce a more deployment-friendly default config search path in the CLI, or leave config path behavior unchanged for now.
