# NixOS module for traktor-m3u-sync.
#
# Exposes two independent oneshot services (export and import) under
# `services.traktor-m3u-sync`.  The module renders a TOML configuration
# file from declarative Nix settings and invokes the CLI with
# `--config <path>`.
#
# Orchestration policy (timers, path triggers, Syncthing hooks) is
# intentionally out of scope — attach downstream as needed.

{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.traktor-m3u-sync;
  format = pkgs.formats.toml { };

  nonNull = lib.filterAttrs (_: v: v != null);

  configData = {
    library = nonNull cfg.library;
  }
  // lib.optionalAttrs cfg.export.enable {
    export = nonNull {
      inherit (cfg.export) collection_path output_dir;
    };
  }
  // lib.optionalAttrs cfg.import.enable {
    import = nonNull {
      inherit (cfg.import) collection_path import_dir sandbox_name;
    };
  };

  generatedConfigFile = format.generate "traktor-m3u-sync.toml" configData;

  # Use explicit configFile override when provided, otherwise use generated.
  effectiveConfigFile = if cfg.configFile != null then cfg.configFile else generatedConfigFile;

  commonServiceConfig = {
    Type = "oneshot";
    # Fail loudly on bad config; propagate exit code.
    Restart = "no";
  };
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

    library = {
      traktor_root = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/traktor";
        description = ''
          Traktor library root directory (host path).
          Rendered into the TOML config `[library]` table.
          Accepts any string — including Windows-style paths — since
          this is a runtime config value, not a Nix store path.
        '';
      };

      m3u_root = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/playlists";
        description = ''
          M3U library root directory (host path).
          Rendered into the TOML config `[library]` table.
          Accepts any string — including Windows-style paths — since
          this is a runtime config value, not a Nix store path.
        '';
      };
    };

    export = {
      enable = lib.mkEnableOption "traktor-m3u-sync export oneshot service";

      collection_path = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/traktor/collection.nml";
        description = ''
          Path to the Traktor collection.nml file.
          Rendered into the TOML config `[export]` table.
        '';
      };

      output_dir = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/playlists/exported";
        description = ''
          Directory where exported .m3u8 playlist files are written.
          Rendered into the TOML config `[export]` table.
        '';
      };
    };

    import = {
      enable = lib.mkEnableOption "traktor-m3u-sync import oneshot service";

      collection_path = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/traktor/collection.nml";
        description = ''
          Path to the Traktor collection.nml file.
          Rendered into the TOML config `[import]` table.
        '';
      };

      import_dir = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/data/playlists/to-import";
        description = ''
          Directory containing .m3u8 playlists to import.
          Rendered into the TOML config `[import]` table.
        '';
      };

      sandbox_name = lib.mkOption {
        type = lib.types.str;
        default = "Imported Playlists";
        description = ''
          Name of the sandbox folder in collection.nml.
          Rendered into the TOML config `[import]` table.
        '';
      };
    };
  };

  config = lib.mkMerge [
    (lib.mkIf cfg.enable {
      # When using generated config, validate required options are set.
      assertions = lib.optionals (cfg.configFile == null) [
        {
          assertion = cfg.library.traktor_root != null;
          message = "services.traktor-m3u-sync.library.traktor_root is required when using generated config (no configFile override).";
        }
        {
          assertion = cfg.library.m3u_root != null;
          message = "services.traktor-m3u-sync.library.m3u_root is required when using generated config (no configFile override).";
        }
      ];
    })

    (lib.mkIf (cfg.enable && cfg.export.enable) {
      assertions = lib.optionals (cfg.configFile == null) [
        {
          assertion = cfg.export.collection_path != null;
          message = "services.traktor-m3u-sync.export.collection_path is required when export is enabled.";
        }
        {
          assertion = cfg.export.output_dir != null;
          message = "services.traktor-m3u-sync.export.output_dir is required when export is enabled.";
        }
      ];

      systemd.services.traktor-m3u-sync-export = {
        description = "Traktor M3U playlist export";
        wantedBy = [ ];
        after = [ ];
        serviceConfig = commonServiceConfig // {
          ExecStart = lib.concatStringsSep " " [
            (lib.getExe cfg.package)
            "export"
            "--config"
            (toString effectiveConfigFile)
          ];
        };
      };
    })

    (lib.mkIf (cfg.enable && cfg.import.enable) {
      assertions = lib.optionals (cfg.configFile == null) [
        {
          assertion = cfg.import.collection_path != null;
          message = "services.traktor-m3u-sync.import.collection_path is required when import is enabled.";
        }
        {
          assertion = cfg.import.import_dir != null;
          message = "services.traktor-m3u-sync.import.import_dir is required when import is enabled.";
        }
      ];

      systemd.services.traktor-m3u-sync-import = {
        description = "Traktor M3U playlist import";
        wantedBy = [ ];
        after = [ ];
        serviceConfig = commonServiceConfig // {
          ExecStart = lib.concatStringsSep " " [
            (lib.getExe cfg.package)
            "import"
            "--config"
            (toString effectiveConfigFile)
          ];
        };
      };
    })
  ];
}
