## 1. Add runtime packaging outputs

- [x] 1.1 Extend `flake.nix` to expose a real runtime package output for `traktor-m3u-sync` alongside the existing developer shell outputs.
- [x] 1.2 Add a flake app output that runs the packaged CLI through `nix run` using the packaged runtime artifact.
- [x] 1.3 Add any Nix-side Python dependency packaging or overrides needed so the package builds reproducibly with its runtime dependencies.

## 2. Add declarative module integration

- [x] 2.1 Add a generic NixOS module that exposes separate oneshot `export` and `import` service surfaces with an overridable `package` option.
- [x] 2.2 Implement declarative TOML configuration rendering for the module and wire the services to invoke the CLI with an explicit `--config` path.
- [x] 2.3 Keep orchestration policy out of the base module by documenting or structuring downstream attachment points instead of bundling timers or path triggers.

## 3. Align local workflow and docs

- [x] 3.1 Extend the canonical local workflow so developers can verify package and app outputs through standardized repo commands or checks.
- [x] 3.2 Update README, PLAN, and any affected canonical docs to describe the new packaging/module surfaces, boundaries, and downstream orchestration expectations.

## 4. Validate deployment-facing outputs

- [x] 4.1 Add targeted validation for the new flake package/app/module surfaces.
- [x] 4.2 Run the relevant project checks and strict OpenSpec validation for the completed deployment-packaging change.
