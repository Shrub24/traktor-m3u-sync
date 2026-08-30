# NixOS module for traktor-m3u-sync.
#
# Exposes two independent oneshot services (export and import) under
# `services.traktor-m3u-sync`.  The module renders a TOML configuration
# file from declarative Nix settings and invokes the CLI with
# `export|import --format <nml|m3u|itunes> --config <path>`.
#
# Orchestration policy (timers, path triggers, Syncthing hooks) is
# intentionally out of scope — attach downstream as needed.

{
  config,
  lib,
  pkgs,
  utils,
  ...
}:

let
  cfg = config.services.traktor-m3u-sync;
  format = pkgs.formats.toml { };

  nonNull = lib.filterAttrs (_: v: v != null);

  importFormatType = lib.types.enum [
    "nml"
    "m3u"
  ];

  exportFormatType = lib.types.enum [
    "nml"
    "m3u"
    "itunes"
  ];

  nmlSelected =
    (cfg.export.enable && cfg.export.format == "nml")
    || (cfg.import.enable && cfg.import.format == "nml");
  m3uSelected =
    (cfg.export.enable && cfg.export.format == "m3u")
    || (cfg.import.enable && cfg.import.format == "m3u");
  itunesSelected = cfg.export.enable && cfg.export.format == "itunes";

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
    && !(builtins.match ".*[^!-~].*" uri != null)
    && builtins.match "^[^%]*(%[0-9A-Fa-f]{2}[^%]*)*$" uri != null
    && builtins.match "^[^?#]*$" uri != null
    && validFileUriAuthority authority;

  configData = {
    store = nonNull cfg.store;
  }
  // lib.optionalAttrs nmlSelected { nml = nonNull cfg.nml; }
  // lib.optionalAttrs m3uSelected { m3u = nonNull cfg.m3u; }
  // lib.optionalAttrs itunesSelected { itunes = nonNull cfg.itunes; };

  generatedConfigFile = format.generate "traktor-m3u-sync.toml" configData;

  # Use explicit configFile override when provided, otherwise use generated.
  effectiveConfigFile = if cfg.configFile != null then cfg.configFile else generatedConfigFile;

  commonServiceConfig = {
    Type = "oneshot";
    # Fail loudly on bad config; propagate exit code.
    Restart = "no";
  };

  serviceExec =
    subcommand: serviceCfg:
    utils.escapeSystemdExecArgs (
      [
        (lib.getExe cfg.package)
        subcommand
        "--format"
        serviceCfg.format
        "--config"
        (toString effectiveConfigFile)
      ]
      ++ serviceCfg.extraArgs
    );
in
{
  options.services.traktor-m3u-sync = {
    enable = lib.mkEnableOption "traktor-m3u-sync deployment services";

    package = lib.mkPackageOption pkgs "traktor-m3u-sync" { };

    configFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      example = "/etc/traktor-m3u-sync/config.toml";
      description = ''
        Override the generated TOML config with an explicit file path.
        When set, the module uses this file instead of rendering config
        from the Nix options below. In that mode, the service-specific
        runtime values are expected to come from the external TOML file
        rather than these Nix options.
      '';
    };

    store = {
      path = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/var/lib/traktor-m3u-sync/store.db";
        description = ''
          SQLite store database path. Rendered into the TOML config
          `[store]` table; null leaves the tool's default location.
        '';
      };
    };

    nml = {
      library_root = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "M:\\Music";
        description = ''
          NML library root directory. Rendered into the TOML config `[nml]`
          table and required for services whose format is `nml`.
        '';
      };

      collection_path = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/traktor/collection.nml";
        description = ''
          Path to the Traktor collection.nml file.
          Rendered into the TOML config `[nml]` table.
          Required for services whose format is `nml`.
        '';
      };

      sandbox_name = lib.mkOption {
        type = lib.types.str;
        default = "Imported Playlists";
        description = ''
          Name of the sandbox folder in collection.nml.
          Rendered into the TOML config `[nml]` table.
        '';
      };
    };

    m3u = {
      library_root = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/music";
        description = ''
          M3U library root directory. Rendered into the TOML config `[m3u]`
          table and required for services whose format is `m3u`.
        '';
      };

      output_dir = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/playlists/exported";
        description = ''
          Directory where exported .m3u8 playlist files are written.
          Rendered into the TOML config `[m3u]` table.
          Required when export.format is `m3u`.
        '';
      };

      import_dir = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/playlists/to-import";
        description = ''
          Directory containing .m3u8 playlists to import.
          Rendered into the TOML config `[m3u]` table.
          Required when import.format is `m3u`.
        '';
      };
    };

    itunes = {
      output_file = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/playlists/iTunes Music Library.xml";
        description = ''
          Path to the generated iTunes Music Library XML file.
          Rendered into the TOML config `[itunes]` table.
          Required when export.format is `itunes`.
        '';
      };

      location_base = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "file://localhost/M:/Music";
        description = ''
          Complete absolute `file:` URI used to construct iTunes track Locations.
          Rendered into the TOML config `[itunes]` table.
          Required when export.format is `itunes`.
        '';
      };

      check_base_path = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/srv/music";
        description = ''
          Optional local worker path used only for iTunes missing-file warnings.
          Rendered into the TOML config `[itunes]` table.
        '';
      };
    };

    export = {
      enable = lib.mkEnableOption "traktor-m3u-sync export oneshot service";

      format = lib.mkOption {
        type = lib.types.nullOr exportFormatType;
        default = null;
        example = "m3u";
        description = ''
          Target format for the export service (`m3u`, `nml`, or `itunes`).
          Passed as `--format` on the command line; selects which
          config fields must be set.
        '';
      };

      extraArgs = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        example = [ "--fail-on-warning" ];
        description = "Additional CLI arguments appended after --format and --config.";
      };
    };

    import = {
      enable = lib.mkEnableOption "traktor-m3u-sync import oneshot service";

      format = lib.mkOption {
        type = lib.types.nullOr importFormatType;
        default = null;
        example = "nml";
        description = ''
          Source format for the import service (`nml` or `m3u`).
          Passed as `--format` on the command line; selects which
          config fields must be set.
        '';
      };

      extraArgs = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        example = [ "--fail-on-warning" ];
        description = "Additional CLI arguments appended after --format and --config.";
      };
    };
  };

  config = lib.mkMerge [
    (lib.mkIf (cfg.enable && cfg.export.enable) {
      assertions = [
        {
          assertion = cfg.export.format != null;
          message = "services.traktor-m3u-sync.export.format is required when export is enabled.";
        }
      ]
      ++ lib.optionals (cfg.configFile == null && cfg.export.format == "m3u") [
        {
          assertion = cfg.m3u.library_root != null;
          message = "services.traktor-m3u-sync.m3u.library_root is required when export.format is m3u.";
        }
        {
          assertion = cfg.m3u.output_dir != null;
          message = "services.traktor-m3u-sync.m3u.output_dir is required when export.format is m3u.";
        }
      ]
      ++ lib.optionals (cfg.configFile == null && cfg.export.format == "nml") [
        {
          assertion = cfg.nml.library_root != null;
          message = "services.traktor-m3u-sync.nml.library_root is required when export.format is nml.";
        }
        {
          assertion = cfg.nml.collection_path != null;
          message = "services.traktor-m3u-sync.nml.collection_path is required when export.format is nml.";
        }
      ]
      ++ lib.optionals (cfg.configFile == null && cfg.export.format == "itunes") [
        {
          assertion = cfg.itunes.output_file != null;
          message = "services.traktor-m3u-sync.itunes.output_file is required when export.format is itunes.";
        }
        {
          assertion = cfg.itunes.location_base != null;
          message = "services.traktor-m3u-sync.itunes.location_base is required when export.format is itunes.";
        }
        {
          assertion = cfg.itunes.location_base != null && validFileUri cfg.itunes.location_base;
          message = "services.traktor-m3u-sync.itunes.location_base must be a complete absolute file: URI when export.format is itunes.";
        }
      ];

      systemd.services.traktor-m3u-sync-export = {
        description = "Traktor M3U playlist export";
        wantedBy = [ ];
        after = [ ];
        serviceConfig = commonServiceConfig // {
          ExecStart = serviceExec "export" cfg.export;
        };
      };
    })

    (lib.mkIf (cfg.enable && cfg.import.enable) {
      assertions = [
        {
          assertion = cfg.import.format != null;
          message = "services.traktor-m3u-sync.import.format is required when import is enabled.";
        }
      ]
      ++ lib.optionals (cfg.configFile == null && cfg.import.format == "m3u") [
        {
          assertion = cfg.m3u.library_root != null;
          message = "services.traktor-m3u-sync.m3u.library_root is required when import.format is m3u.";
        }
        {
          assertion = cfg.m3u.import_dir != null;
          message = "services.traktor-m3u-sync.m3u.import_dir is required when import.format is m3u.";
        }
      ]
      ++ lib.optionals (cfg.configFile == null && cfg.import.format == "nml") [
        {
          assertion = cfg.nml.library_root != null;
          message = "services.traktor-m3u-sync.nml.library_root is required when import.format is nml.";
        }
        {
          assertion = cfg.nml.collection_path != null;
          message = "services.traktor-m3u-sync.nml.collection_path is required when import.format is nml.";
        }
      ];

      systemd.services.traktor-m3u-sync-import = {
        description = "Traktor M3U playlist import";
        wantedBy = [ ];
        after = [ ];
        serviceConfig = commonServiceConfig // {
          ExecStart = serviceExec "import" cfg.import;
        };
      };
    })
  ];
}
