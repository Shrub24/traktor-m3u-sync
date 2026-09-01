## 1. Module identity options

- [x] 1.1 Add `user`, `group`, and `supplementaryGroups` options to `nix/modules/traktor-m3u-sync.nix`; create only the default `playlist-sync` user/group; wire `User=`/`Group=`/`SupplementaryGroups=` into `commonServiceConfig`.
  - refs: openspec/changes/service-identity/specs/deployment-packaging/spec.md
  - criteria: default identity yields a system user with `isSystemUser`, a non-login shell, and `group = "playlist-sync"`; non-root generated config requires `store.path`; `user = null` omits `User=`/`Group=` and creates no account; custom names are operator-managed.

## 2. Verification

- [x] 2.1 Evaluate the existing representative module fixture through `nix flake check`; rely on module assertions for invalid identity combinations rather than adding a synthetic identity matrix.
  - depends: 1.1
  - verify: nix flake check

## 3. Documentation

- [x] 3.1 Update `docs/nix-deployment.md`, `ARCHITECTURE.md`, and `PLAN.md` with the new options, neutral service-identity decision, and the one-time operator step for granting access to store/library paths.
  - depends: 1.1

## 4. Close-out

- [x] 4.1 Run `just check`, `nix flake check`, and `openspec validate service-identity --strict`.
  - depends: 2.1, 3.1
