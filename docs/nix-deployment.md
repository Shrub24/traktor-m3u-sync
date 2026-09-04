# Nix Deployment Reference

## Flake outputs

The flake exposes the runtime package and app, development shell, formatting and module-evaluation checks, and `nixosModules.traktor-m3u-sync` (`nixosModules.default` is an alias). Supported systems are `x86_64-linux` and `aarch64-linux`.

## NixOS module

All options live under `services.traktor-m3u-sync`. The module declares named state domains and independently triggerable action jobs. It creates no timer, path unit, consumer hook, or implicit Engine schedule.

### Shared options

| Option | Type | Default | Description |
|---|---|---|---|
| `enable` | bool | `false` | Generate declared jobs |
| `package` | package | flake package | CLI package used by all jobs |
| `user` | null/string | `"playlist-sync"` | Shared service user; `null` runs as root |
| `group` | null/string | `"playlist-sync"` | Shared primary group; must be null with a null user |
| `supplementaryGroups` | list of strings | `[]` | Existing groups added to every job |
| `states.<name>.path` | string | required | Explicit writable SQLite path for this isolated state |

State paths must be absolute and distinct. At most one import job may rebuild a state; any number of exports may read it. The default `playlist-sync` system user and group are created only when both default names are retained. Keep that primary identity and use `supplementaryGroups` for access to operator-managed media groups; custom matching user/group names are available when the whole identity is operator-managed.

### Job options

Job names must match `^[A-Za-z0-9][A-Za-z0-9_-]*$`; names are never silently rewritten. A job is exposed as `traktor-m3u-sync-<action>@<name>.service`.

| Option | Type | Default | Description |
|---|---|---|---|
| `jobs.<name>.action` | `"import"` or `"export"` | required | Exactly one CLI action |
| `jobs.<name>.state` | string | required | Existing state name |
| `jobs.<name>.format` | enum | required | Import: `nml`, `m3u`; export: `nml`, `m3u`, `itunes`, `engine` |
| `jobs.<name>.configFile` | null/string | `null` | External authoritative TOML instead of generated settings |
| `jobs.<name>.extraArgs` | list of strings | `[]` | Distinct CLI arguments appended after format/config |
| `jobs.<name>.onSuccess` | list of job names | `[]` | Jobs started only after status 0; missing, self, and cyclic references are rejected |
| `jobs.<name>.onFailure` | list of job names | `[]` | Jobs started when the instance fails; validated like `onSuccess` |
| `jobs.<name>.reportFile` | null/string | `null` | Path for the JSON run report (`--report-file`) |
| `jobs.<name>.nml.library_root` | null/string | `null` | Required for generated NML jobs |
| `jobs.<name>.nml.collection_path` | null/string | `null` | Required for generated NML jobs |
| `jobs.<name>.nml.sandbox_name` | string | `"Imported Playlists"` | NML sandbox folder |
| `jobs.<name>.m3u.library_root` | null/string | `null` | Required for generated M3U jobs |
| `jobs.<name>.m3u.import_dir` | null/string | `null` | Required for generated M3U imports |
| `jobs.<name>.m3u.output_dir` | null/string | `null` | Required for generated M3U exports |
| `jobs.<name>.itunes.output_file` | null/string | `null` | Required for generated iTunes exports |
| `jobs.<name>.itunes.location_base` | null/string | `null` | Required absolute `file:` URI for iTunes Locations |
| `jobs.<name>.itunes.check_base_path` | null/string | `null` | Optional worker-side missing-file check root |
| `jobs.<name>.engine.database_path` | null/string | `null` | Required existing Engine `m.db` path |
| `jobs.<name>.engine.track_path_prefix` | string | `".."` | Prefix used to match Engine tracks |
| `jobs.<name>.engine.managed_root` | string | `"Playlist Sync"` | Managed Engine playlist subtree |
| `jobs.<name>.engine.check_base_path` | null/string | `null` | Optional worker-side missing-file check root |

Generated jobs receive one TOML file containing `[store]` from their referenced state and only their selected format section. With `configFile`, the external file owns both store and format configuration; selected-format generated settings must not also be set, and the module cannot verify that the external store agrees with the declared state.

## Migration from singleton options

Before:

```nix
services.traktor-m3u-sync = {
  enable = true;
  store.path = "/var/lib/playlist-sync/library.db";
  m3u = {
    library_root = "/mnt/music";
    import_dir = "/mnt/playlists/incoming";
  };
  import = {
    enable = true;
    format = "m3u";
  };
};
```

After:

```nix
services.traktor-m3u-sync = {
  enable = true;
  package = inputs.traktor-m3u-sync.packages.${pkgs.system}.traktor-m3u-sync;
  states.library.path = "/var/lib/playlist-sync/library.db";
  jobs.ingest = {
    action = "import";
    state = "library";
    format = "m3u";
    m3u = {
      library_root = "/mnt/music";
      import_dir = "/mnt/playlists/incoming";
    };
  };
};
```

A fan-out deployment adds exports to the same state:

```nix
services.traktor-m3u-sync.jobs = {
  ingest.onSuccess = [ "itunes" "engine" ];
  itunes = {
    action = "export";
    state = "library";
    format = "itunes";
    itunes = {
      output_file = "/mnt/playlists/iTunes Music Library.xml";
      location_base = "file://localhost/M:/Music";
    };
  };
  engine = {
    action = "export";
    state = "library";
    format = "engine";
    engine.database_path = "/mnt/engine/Engine Library/Database2/m.db";
  };
};
```

## Operation and result semantics

Start and inspect jobs directly:

```console
systemctl start traktor-m3u-sync-import@ingest.service
systemctl status traktor-m3u-sync-export@itunes.service
journalctl -u traktor-m3u-sync-export@engine.service
```

`onSuccess` fan-out is asynchronous. Status `0` starts targets; status `1`, or status `2` from `--fail-on-warning`, does not. `onFailure` targets start when the instance fails instead. A downstream failure appears on that target unit and does not change the completed source result. `--dry-run` and `--fail-on-warning` belong in `extraArgs` as separate list items.

Every command records its store origin (`source_format`, `imported_at`) in export summaries, and `--report-file` (or per-job `reportFile`) persists a JSON run report with counts, warnings, provenance, and exit status — including a report on hard failures and a `dry_run` marker on rehearsals. An import whose non-empty source yields zero playlists warns `empty_import_source`, so strict-mode automation trips on silent-empty scans.

Engine DJ must remain closed for an Engine export. The module does not create, chown, mount, schedule, or grant access to its database. The shared service identity needs access to every state and adapter path; Engine publication additionally needs create-and-rename access in the database directory.

## Downstream orchestration examples

Daily timer for one export:

```nix
systemd.timers."traktor-m3u-sync-export@itunes" = {
  wantedBy = [ "timers.target" ];
  timerConfig = {
    Unit = "traktor-m3u-sync-export@itunes.service";
    OnCalendar = "03:00";
    Persistent = true;
  };
};
```

Path-triggered import:

```nix
systemd.paths."traktor-m3u-sync-import@ingest" = {
  wantedBy = [ "paths.target" ];
  pathConfig = {
    PathModified = "/mnt/playlists/incoming";
    Unit = "traktor-m3u-sync-import@ingest.service";
  };
};
```

Export before a consumer starts:

```nix
systemd.services.navidrome = {
  requires = [ "traktor-m3u-sync-export@navidrome.service" ];
  after = [ "traktor-m3u-sync-export@navidrome.service" ];
};
```

Coordinate Engine availability downstream rather than with a timer; for example, start `traktor-m3u-sync-export@engine.service` only after the operator or host automation has closed Engine DJ.

## `traktor-nml-utils` packaging

The flake packages the PyPI dependency as `packages.<system>.traktor-nml-utils` and includes it in the runtime application. No separate operator setup is required.
