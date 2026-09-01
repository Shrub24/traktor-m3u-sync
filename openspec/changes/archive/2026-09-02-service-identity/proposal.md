## Why

The module's oneshot units define no `User`/`Group`, so they run as root — the widest possible blast radius for a service that reads the music library and writes the store, M3U, NML, and iTunes XML targets. NixOS convention for a stateful service is a module-created dedicated system account, not root and not a pre-created operator user. `DynamicUser=` is unsuitable because the service writes operator-configured paths outside its own state directory.

## What Changes

- The NixOS module declares `user` and `group` options (default `playlist-sync` — deliberately product-name-neutral) plus `supplementaryGroups` for shared media access.
- When enabled with the default identity, the module creates the system group and user (Nixpkgs-allocated UID, no login). Any custom `user`/`group` name is treated as operator-managed and is not created; `user = null` runs the units as root.
- Generated import/export units gain `User=`/`Group=` and optional `SupplementaryGroups=` accordingly. Non-root generated configurations require an explicit `store.path`, avoiding the CLI's unwritable home-relative fallback.
- Deployment docs state the operator obligation: grant the service identity access to store/library paths (ownership, group, or ACLs).

## Capabilities

### Modified Capabilities
- `deployment-packaging`: service integration runs under a configurable non-root identity by default.

## Impact

- **Nix:** `nix/modules/traktor-m3u-sync.nix` options + `users.*` config + `commonServiceConfig`; flake module-eval fixture assertions.
- **Docs:** `docs/nix-deployment.md` option table and permission guidance.
- **Homelab:** first switch needs one-time `chown`/ACLs on `/srv/data/traktor-m3u-sync` and the iTunes output path.
- No Python, config-schema, or CLI changes.
