# Nix Deployment Reference

Concise reference for building, deploying, and operating `traktor-m3u-sync`
via Nix.

## Flake outputs

| Output | Description |
|---|---|
| `packages.<system>.traktor-m3u-sync` | Runtime package (Python 3.14, hatchling build) |
| `packages.<system>.traktor-nml-utils` | Vendored dependency (not in nixpkgs) |
| `packages.<system>.default` | Alias for `traktor-m3u-sync` |
| `apps.<system>.default` | `nix run` entry point |
| `devShells.<system>.default` | Dev shell with git, just, lefthook, python314, pyright, ruff, treefmt, uv |
| `checks.<system>.formatting` | treefmt formatting check |
| `checks.<system>.module-eval` | NixOS module evaluation smoke test |
| `nixosModules.traktor-m3u-sync` | NixOS module |
| `nixosModules.default` | Alias for the module |

Supported systems: `x86_64-linux`, `aarch64-linux`.

## NixOS module options

All options live under `services.traktor-m3u-sync.*`.

| Option | Type | Default | Description |
|---|---|---|---|
| `enable` | bool | `false` | Enable the traktor-m3u-sync services |
| `package` | package | flake package | Override the runtime package |
| `configFile` | null/path | `null` | External TOML config (overrides generated config) |
| `library.traktor_root` | string | — | Traktor library root (Windows path format) |
| `library.m3u_root` | string | — | M3U library root |
| `export.enable` | bool | `false` | Enable the export oneshot service |
| `export.collection_path` | null/string | `null` | Path to `collection.nml` |
| `export.output_dir` | null/string | `null` | Directory for generated `.m3u8` files |
| `import.enable` | bool | `false` | Enable the import oneshot service |
| `import.collection_path` | null/string | `null` | Path to `collection.nml` |
| `import.import_dir` | null/string | `null` | Directory containing M3U files to import |
| `import.sandbox_name` | string | `"Imported Playlists"` | Sandbox folder name in Traktor |

The module creates two systemd oneshot services:

- `traktor-m3u-sync-export.service`
- `traktor-m3u-sync-import.service`

Both have `wantedBy = []` by default — they are never triggered automatically.

## Config file override

When `configFile` is set, the module uses the external TOML file directly
instead of generating one from Nix options. In that mode:

- `library.*`, `export.*`, and `import.*` Nix options are still used for
  service enablement but do not affect the runtime config file
- The runtime workflow values come entirely from the external file
- Use this for externally managed configs (e.g. Syncthing-deployed files)

```nix
services.traktor-m3u-sync = {
  enable = true;
  configFile = "/etc/traktor-m3u-sync/config.toml";
  export.enable = true;
  import.enable = true;
};
```

## Downstream orchestration

Services are oneshot units with no bundled timers or triggers. Attach
scheduling in your own NixOS config.

### Export timer (daily at 03:00)

```nix
systemd.timers.traktor-m3u-sync-export = {
  wantedBy = [ "timers.target" ];
  timerConfig = {
    OnCalendar = "03:00";
    Persistent = true;
  };
};
```

### Import timer (every 15 minutes)

```nix
systemd.timers.traktor-m3u-sync-import = {
  wantedBy = [ "timers.target" ];
  timerConfig = {
    OnCalendar = "*:0/15";
    Persistent = true;
  };
};
```

### Syncthing folder watch

For Syncthing-managed setups, use a path unit that triggers import when
the playlist directory changes:

```nix
systemd.paths.traktor-m3u-sync-import = {
  wantedBy = [ "paths.target" ];
  pathConfig = {
    PathModified = "/mnt/playlists";
    Unit = "traktor-m3u-sync-import.service";
  };
};
```

## traktor-nml-utils packaging

[`traktor-nml-utils`](https://github.com/wolkenarchitekt/traktor-nml-utils)
is not available in nixpkgs. The flake packages it from PyPI as a vendored
derivation (`nix/packages/traktor-nml-utils.nix`):

- Source: PyPI sdist (currently v4.1.0)
- Build dependency: `setuptools`
- Runtime dependencies: `typer`, `xsdata`
- Tests: disabled (`doCheck = false`) — upstream has no pytest suite
- License: GPL-3.0-only

The package is exposed as `packages.<system>.traktor-nml-utils` and
consumed automatically by the main `traktor-m3u-sync` package. No manual
intervention needed unless you need to override the version.
