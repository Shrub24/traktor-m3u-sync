## Context

The generic NixOS module currently leaves `User=` unset, so both oneshots run as root. The worker persists a SQLite store and writes operator-configured targets outside a module-owned state directory, making systemd `DynamicUser=` unsuitable. Deployments may also need a shared media group or an existing service identity.

## Decisions

### D1: Stable neutral default identity

The module defaults to a product-neutral `playlist-sync` user and group. It creates a system user/group only when both configured names equal that default. A custom identity must provide both names and is treated as operator-managed. No numeric UID/GID is fixed; NixOS allocates the default account.

`user = null` deliberately omits `User=` and `Group=`, preserving an explicit root escape hatch.

### D2: Shared group access is configurable

A shared `supplementaryGroups` list maps to systemd `SupplementaryGroups=` for both import and export units. The base module does not hard-code a site-specific `media` group.

### D3: Filesystem sandbox paths remain downstream policy

The base module does not add `ReadOnlyPaths=` or `ReadWritePaths=`. Those directives restrict systemd's filesystem namespace; they do not grant Unix permissions. Required paths are operator-configurable (or hidden behind `configFile`), so homelab configuration owns path-specific sandboxing and ACL/ownership policy.

## Migration

The first switch creates `playlist-sync`. Before starting either unit, the operator grants it or one of its supplementary groups access to the configured import/store/output paths. A future account rename is a module-option change plus ownership/ACL adjustment; no application state migration is involved.
