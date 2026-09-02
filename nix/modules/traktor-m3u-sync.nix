# NixOS module for named traktor-m3u-sync state domains and action jobs.
{
  config,
  lib,
  pkgs,
  utils,
  ...
}:

let
  cfg = config.services.traktor-m3u-sync;
  toml = pkgs.formats.toml { };
  nonNull = lib.filterAttrs (_: value: value != null);

  importFormats = [
    "nml"
    "m3u"
  ];
  exportFormats = importFormats ++ [
    "itunes"
    "engine"
  ];

  stateModule = lib.types.submodule {
    options.path = lib.mkOption {
      type = lib.types.str;
      example = "/var/lib/playlist-sync/library.db";
      description = "Explicit absolute writable SQLite store path for this state domain.";
    };
  };

  jobModule = lib.types.submodule {
    options = {
      action = lib.mkOption {
        type = lib.types.enum [
          "import"
          "export"
        ];
        description = "Single CLI action performed by this job.";
      };

      state = lib.mkOption {
        type = lib.types.str;
        description = "Name of the state domain used by this job.";
      };

      format = lib.mkOption {
        type = lib.types.enum exportFormats;
        description = "Import source or export target format.";
      };

      configFile = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/etc/playlist-sync/config.toml";
        description = "External TOML file used instead of generated job settings.";
      };

      extraArgs = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        example = [ "--fail-on-warning" ];
        description = "Arguments appended after the explicit format and config arguments.";
      };

      onSuccess = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        description = "Configured jobs started after this job succeeds.";
      };

      nml = {
        library_root = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "M:\\Music";
        };
        collection_path = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "/data/traktor/collection.nml";
        };
        sandbox_name = lib.mkOption {
          type = lib.types.str;
          default = "Imported Playlists";
        };
      };

      m3u = {
        library_root = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "/data/music";
        };
        output_dir = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "/data/playlists/exported";
        };
        import_dir = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "/data/playlists/to-import";
        };
      };

      itunes = {
        output_file = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "/data/playlists/iTunes Music Library.xml";
        };
        location_base = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "file://localhost/M:/Music";
        };
        check_base_path = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "/srv/music";
        };
      };

      engine = {
        database_path = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          example = "/mnt/engine/Engine Library/Database2/m.db";
        };
        track_path_prefix = lib.mkOption {
          type = lib.types.str;
          default = "..";
        };
        managed_root = lib.mkOption {
          type = lib.types.str;
          default = "Playlist Sync";
        };
      };
    };
  };

  jobs = cfg.jobs;
  jobNames = builtins.attrNames jobs;
  selectedFormatSettings = job: {
    nml = [
      job.nml.library_root
      job.nml.collection_path
      (if job.nml.sandbox_name == "Imported Playlists" then null else job.nml.sandbox_name)
    ];
    m3u = [
      job.m3u.library_root
      job.m3u.output_dir
      job.m3u.import_dir
    ];
    itunes = [
      job.itunes.output_file
      job.itunes.location_base
      job.itunes.check_base_path
    ];
    engine = [
      job.engine.database_path
      (if job.engine.track_path_prefix == ".." then null else job.engine.track_path_prefix)
      (if job.engine.managed_root == "Playlist Sync" then null else job.engine.managed_root)
    ];
  };

  validFileUriAuthority =
    authority:
    authority == ""
    || authority == "localhost"
    || (
      builtins.match "^[A-Za-z0-9._~!$&'()*+,;=%-]+$" authority != null
      && builtins.match "^-.*|.*-$" authority == null
    );

  validFileUri =
    uri:
    let
      remainder = lib.removePrefix "file://" uri;
      parts = lib.splitString "/" remainder;
      authority = builtins.head parts;
    in
    lib.hasPrefix "file://" uri
    && builtins.length parts > 1
    && builtins.match "[!-~]*" uri != null
    && builtins.match "^[^%]*(%[0-9A-Fa-f]{2}[^%]*)*$" uri != null
    && builtins.match "^[^?#]*$" uri != null
    && validFileUriAuthority authority;

  jobUnitName = name: "traktor-m3u-sync-${jobs.${name}.action}@${name}.service";

  generatedConfig =
    name: job:
    toml.generate "traktor-m3u-sync-${name}.toml" (
      {
        store.path = cfg.states.${job.state}.path or "/invalid-missing-state";
      }
      // lib.setAttrByPath [ job.format ] (nonNull job.${job.format})
    );

  effectiveConfig =
    name: job: if job.configFile != null then job.configFile else generatedConfig name job;

  jobExec =
    name: job:
    utils.escapeSystemdExecArgs (
      [
        (lib.getExe cfg.package)
        job.action
        "--format"
        job.format
        "--config"
        (toString (effectiveConfig name job))
      ]
      ++ job.extraArgs
    );

  commonServiceConfig = {
    Type = "oneshot";
    Restart = "no";
  }
  // lib.optionalAttrs (cfg.user != null) {
    User = cfg.user;
    Group = cfg.group;
  }
  // lib.optionalAttrs (cfg.user != null && cfg.supplementaryGroups != [ ]) {
    SupplementaryGroups = cfg.supplementaryGroups;
  };

  templateService = action: {
    description = "Playlist sync ${action} job %i";
    wantedBy = [ ];
    after = [ ];
    serviceConfig = commonServiceConfig // {
      ExecStart = "${lib.getExe cfg.package} ${action}";
    };
  };

  instanceService =
    name: job:
    lib.nameValuePair "traktor-m3u-sync-${job.action}@${name}" {
      description = "Playlist sync ${job.action} job ${name}";
      overrideStrategy = "asDropin";
      unitConfig.OnSuccess = map jobUnitName job.onSuccess;
      serviceConfig.ExecStart = [
        ""
        (jobExec name job)
      ];
    };

  importsForState =
    stateName:
    lib.filter (name: jobs.${name}.action == "import" && jobs.${name}.state == stateName) jobNames;

  hasCycleFrom =
    path: name:
    lib.elem name path
    || (builtins.hasAttr name jobs && lib.any (hasCycleFrom (path ++ [ name ])) jobs.${name}.onSuccess);

  stateAssertions = lib.mapAttrsToList (name: state: {
    assertion = lib.hasPrefix "/" state.path;
    message = "services.traktor-m3u-sync.states.${name}.path must be an absolute runtime path.";
  }) cfg.states;

  jobAssertions = lib.concatMap (
    name:
    let
      job = jobs.${name};
      prefix = "services.traktor-m3u-sync.jobs.${name}";
      generated = job.configFile == null;
    in
    [
      {
        assertion = builtins.match "^[A-Za-z0-9][A-Za-z0-9_-]*$" name != null;
        message = "${prefix}: job names must match ^[A-Za-z0-9][A-Za-z0-9_-]*$.";
      }
      {
        assertion = builtins.hasAttr job.state cfg.states;
        message = "${prefix}.state references missing state '${job.state}'.";
      }
      {
        assertion = job.action == "export" || lib.elem job.format importFormats;
        message = "${prefix}.format '${job.format}' is not supported for import jobs.";
      }
      {
        assertion = lib.all (target: builtins.hasAttr target jobs) job.onSuccess;
        message = "${prefix}.onSuccess references a missing job.";
      }
      {
        assertion = !(lib.elem name job.onSuccess);
        message = "${prefix}.onSuccess must not reference itself.";
      }
      {
        assertion = !(hasCycleFrom [ ] name);
        message = "${prefix}.onSuccess reaches a cycle.";
      }
      {
        assertion =
          job.configFile == null || lib.all (value: value == null) (selectedFormatSettings job).${job.format};
        message = "${prefix}.configFile cannot be combined with selected-format generated settings.";
      }
    ]
    ++ lib.optionals (generated && job.format == "nml") [
      {
        assertion = job.nml.library_root != null;
        message = "${prefix}.nml.library_root is required for generated NML config.";
      }
      {
        assertion = job.nml.collection_path != null;
        message = "${prefix}.nml.collection_path is required for generated NML config.";
      }
    ]
    ++ lib.optionals (generated && job.action == "import" && job.format == "m3u") [
      {
        assertion = job.m3u.library_root != null;
        message = "${prefix}.m3u.library_root is required for generated M3U import config.";
      }
      {
        assertion = job.m3u.import_dir != null;
        message = "${prefix}.m3u.import_dir is required for generated M3U import config.";
      }
    ]
    ++ lib.optionals (generated && job.action == "export" && job.format == "m3u") [
      {
        assertion = job.m3u.library_root != null;
        message = "${prefix}.m3u.library_root is required for generated M3U export config.";
      }
      {
        assertion = job.m3u.output_dir != null;
        message = "${prefix}.m3u.output_dir is required for generated M3U export config.";
      }
    ]
    ++ lib.optionals (generated && job.format == "itunes") [
      {
        assertion = job.itunes.output_file != null;
        message = "${prefix}.itunes.output_file is required for generated iTunes config.";
      }
      {
        assertion = job.itunes.location_base != null && validFileUri job.itunes.location_base;
        message = "${prefix}.itunes.location_base must be a complete absolute file: URI.";
      }
    ]
    ++ lib.optionals (generated && job.format == "engine") [
      {
        assertion = job.engine.database_path != null;
        message = "${prefix}.engine.database_path is required for generated Engine config.";
      }
    ]
  ) jobNames;
in
{
  options.services.traktor-m3u-sync = {
    enable = lib.mkEnableOption "named traktor-m3u-sync jobs";
    package = lib.mkPackageOption pkgs "traktor-m3u-sync" { };

    user = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = "playlist-sync";
      description = "Shared account for every generated job; null runs jobs as root.";
    };

    group = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = "playlist-sync";
      description = "Shared primary group; null is valid only when user is null.";
    };

    supplementaryGroups = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Existing groups added to every generated job.";
    };

    states = lib.mkOption {
      type = lib.types.attrsOf stateModule;
      default = { };
      description = "Named isolated playlist-state domains.";
    };

    jobs = lib.mkOption {
      type = lib.types.attrsOf jobModule;
      default = { };
      description = "Named independently triggerable import and export jobs.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.user == null || cfg.group != null;
        message = "services.traktor-m3u-sync.group is required when user is non-null.";
      }
      {
        assertion = cfg.user != null || cfg.group == null;
        message = "services.traktor-m3u-sync.group must be null when user is null.";
      }
      {
        assertion = cfg.user == null || cfg.user == cfg.group;
        message = "services.traktor-m3u-sync.user and group must use the same identity name.";
      }
      {
        assertion =
          lib.length (lib.unique (map (state: state.path) (builtins.attrValues cfg.states)))
          == lib.length (builtins.attrValues cfg.states);
        message = "services.traktor-m3u-sync.states must use distinct store paths.";
      }
      {
        assertion = lib.all (stateName: lib.length (importsForState stateName) <= 1) (
          builtins.attrNames cfg.states
        );
        message = "services.traktor-m3u-sync.states allow at most one import job per state.";
      }
    ]
    ++ stateAssertions
    ++ jobAssertions;

    users.groups = lib.optionalAttrs (cfg.user == "playlist-sync" && cfg.group == "playlist-sync") {
      playlist-sync = { };
    };
    users.users = lib.optionalAttrs (cfg.user == "playlist-sync" && cfg.group == "playlist-sync") {
      playlist-sync = {
        isSystemUser = true;
        group = "playlist-sync";
      };
    };

    systemd.services =
      lib.optionalAttrs (lib.any (name: jobs.${name}.action == "import") jobNames) {
        "traktor-m3u-sync-import@" = templateService "import";
      }
      // lib.optionalAttrs (lib.any (name: jobs.${name}.action == "export") jobNames) {
        "traktor-m3u-sync-export@" = templateService "export";
      }
      // builtins.listToAttrs (lib.mapAttrsToList instanceService jobs);
  };
}
