{
  description = "Nix-first workspace for traktor-m3u-sync";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    treefmt-nix.url = "github:numtide/treefmt-nix";
  };

  outputs =
    {
      self,
      flake-parts,
      nixpkgs,
      treefmt-nix,
      ...
    }@inputs:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      imports = [
        treefmt-nix.flakeModule
      ];

      flake = {
        nixosModules.traktor-m3u-sync = import ./nix/modules/traktor-m3u-sync.nix;
        nixosModules.default = self.nixosModules.traktor-m3u-sync;
      };

      perSystem =
        {
          config,
          pkgs,
          system,
          ...
        }:
        let
          treefmtEval = treefmt-nix.lib.evalModule pkgs ./treefmt.nix;

          python = pkgs.python314;

          traktor-nml-utils = python.pkgs.callPackage ./nix/packages/traktor-nml-utils.nix { };

          traktor-m3u-sync = python.pkgs.buildPythonApplication {
            pname = "traktor-m3u-sync";
            version = "0.1.0";
            pyproject = true;

            src = pkgs.lib.cleanSource ./.;

            build-system = [ python.pkgs.hatchling ];

            dependencies = [
              traktor-nml-utils
              python.pkgs.typer
            ];

            # No pytest shipped in the runtime closure.
            doCheck = false;

            meta = {
              description = "Traktor NML to M3U playlist sync tool";
              homepage = "https://github.com/wolkenarchitekt/traktor-m3u-sync";
              # Repo license is GPL-3.0-or-later, which is compatible with the
              # GPL-3.0-only traktor-nml-utils runtime dependency.
              license = pkgs.lib.licenses.gpl3Plus;
              mainProgram = "traktor-m3u-sync";
            };
          };
        in
        {
          formatter = treefmtEval.config.build.wrapper;

          checks = {
            formatting = treefmtEval.config.build.check self;

            module-eval =
              let
                evaled = nixpkgs.lib.nixosSystem {
                  inherit (pkgs) system;
                  modules = [
                    self.nixosModules.traktor-m3u-sync
                    {
                      services.traktor-m3u-sync = {
                        enable = true;
                        package = traktor-m3u-sync;
                        store.path = "/var/lib/traktor-m3u-sync/store.db";
                        m3u = {
                          library_root = "/mnt/music";
                          import_dir = "/mnt/playlists/import";
                        };
                        itunes = {
                          output_file = "/mnt/playlists/iTunes Music Library.xml";
                          location_base = "file://localhost/M:/Music";
                          check_base_path = "/mnt/music";
                        };
                        export = {
                          enable = true;
                          format = "itunes";
                        };
                        import = {
                          enable = true;
                          format = "m3u";
                        };
                      };
                    }
                  ];
                };

                externalConfigEvaled = nixpkgs.lib.nixosSystem {
                  inherit (pkgs) system;
                  modules = [
                    self.nixosModules.traktor-m3u-sync
                    {
                      services.traktor-m3u-sync = {
                        enable = true;
                        package = traktor-m3u-sync;
                        configFile = "/etc/traktor-m3u-sync/config with % percent.toml";
                        export = {
                          enable = true;
                          format = "m3u";
                          extraArgs = [ "--fail-on-warning" ];
                        };
                        import = {
                          enable = true;
                          format = "m3u";
                          extraArgs = [ "--fail-on-warning" ];
                        };
                      };
                    }
                  ];
                };

                nmlMissingRootEvaled =
                  let
                    # Same rationale as locationBaseEvaled: probe the module's
                    # assertion list rather than the full toplevel.
                    evaled = nixpkgs.lib.nixosSystem {
                      inherit (pkgs) system;
                      modules = [
                        self.nixosModules.traktor-m3u-sync
                        {
                          services.traktor-m3u-sync = {
                            enable = true;
                            package = traktor-m3u-sync;
                            nml.collection_path = "/mnt/traktor/collection.nml";
                            export = {
                              enable = true;
                              format = "nml";
                            };
                          };
                        }
                      ];
                    };
                    moduleFailing = builtins.filter (
                      a: !a.assertion && nixpkgs.lib.hasPrefix "services.traktor-m3u-sync" a.message
                    ) evaled.config.assertions;
                  in
                  {
                    success = moduleFailing == [ ];
                    value = null;
                  };

                locationBaseEvaled =
                  location_base:
                  let
                    # Evaluate the module's own assertion list instead of the
                    # full toplevel: a bare nixosSystem always fails toplevel
                    # on base assertions (fileSystems, boot loader), which
                    # would mask our URI validation inside tryEval.
                    evaled = nixpkgs.lib.nixosSystem {
                      inherit (pkgs) system;
                      modules = [
                        self.nixosModules.traktor-m3u-sync
                        {
                          services.traktor-m3u-sync = {
                            enable = true;
                            package = traktor-m3u-sync;
                            itunes = {
                              output_file = "/mnt/playlists/iTunes Music Library.xml";
                              inherit location_base;
                            };
                            export = {
                              enable = true;
                              format = "itunes";
                            };
                          };
                        }
                      ];
                    };
                    moduleFailing = builtins.filter (
                      a: !a.assertion && nixpkgs.lib.hasPrefix "services.traktor-m3u-sync" a.message
                    ) evaled.config.assertions;
                  in
                  {
                    success = moduleFailing == [ ];
                    value = null;
                  };

                cfg = evaled.config.services.traktor-m3u-sync;

                exportService = evaled.config.systemd.services.traktor-m3u-sync-export;
                importService = evaled.config.systemd.services.traktor-m3u-sync-import;
                externalExportService = externalConfigEvaled.config.systemd.services.traktor-m3u-sync-export;
                externalImportService = externalConfigEvaled.config.systemd.services.traktor-m3u-sync-import;

                # Smoke-test: verify the module option surface exists and
                # evaluates without error, the service ExecStart lines pass
                # their declared --format and --config, and the generated
                # TOML parses without an unselected NML section.
                moduleSurfaceOk = cfg.enable == true;
                exportExecOk =
                  builtins.match ".*\"export\" \"--format\" \"itunes\" \"--config\" .*" exportService.serviceConfig.ExecStart
                  != null;
                importExecOk =
                  builtins.match ".*\"import\" \"--format\" \"m3u\" \"--config\" .*" importService.serviceConfig.ExecStart
                  != null;
                nmlRootValidationOk = !nmlMissingRootEvaled.success;
                validLocationBasesOk = nixpkgs.lib.all (location_base: (locationBaseEvaled location_base).success) [
                  "file:///srv/music"
                  "file://localhost/M:/Music"
                  "file://server/share/music"
                  "file://FS_01/share/music"
                ];
                invalidLocationBasesOk =
                  nixpkgs.lib.all (location_base: !(locationBaseEvaled location_base).success)
                    [
                      "file:///srv/music with spaces"
                      "file:///srv/music%2"
                      "file://user@server/share/music"
                      "file://server:445/share/music"
                      "file://-server/share/music"
                      "file:///srv/music?query"
                      "file:///srv/music#fragment"
                      "file:///srv/café"
                    ];
                externalExportExecOk =
                  builtins.match ".*\"export\" \"--format\" \"m3u\" \"--config\" \"/etc/traktor-m3u-sync/config with %% percent.toml\" \"--fail-on-warning\"" externalExportService.serviceConfig.ExecStart
                  != null;
                externalImportExecOk =
                  builtins.match ".*\"import\" \"--format\" \"m3u\" \"--config\" \"/etc/traktor-m3u-sync/config with %% percent.toml\" \"--fail-on-warning\"" externalImportService.serviceConfig.ExecStart
                  != null;
              in
              pkgs.runCommand "module-eval-test" { nativeBuildInputs = [ traktor-m3u-sync ]; } ''
                set -e

                echo "module-eval: checking option surface"
                ${if moduleSurfaceOk then "" else "echo 'FAIL: enable option not true'; exit 1"}

                echo "module-eval: checking export service ExecStart"
                ${if exportExecOk then "" else "echo 'FAIL: export ExecStart missing expected arguments'; exit 1"}

                echo "module-eval: checking import service ExecStart"
                ${if importExecOk then "" else "echo 'FAIL: import ExecStart missing expected pattern'; exit 1"}

                echo "module-eval: checking NML root validation"
                ${
                  if nmlRootValidationOk then "" else "echo 'FAIL: NML service accepted missing library_root'; exit 1"
                }

                echo "module-eval: checking file URI validation"
                ${
                  if validLocationBasesOk then
                    ""
                  else
                    "echo 'FAIL: valid file URI location_base was rejected'; exit 1"
                }
                ${
                  if invalidLocationBasesOk then
                    ""
                  else
                    "echo 'FAIL: malformed file URI location_base was accepted'; exit 1"
                }

                echo "module-eval: checking external-config export ExecStart"
                ${
                  if externalExportExecOk then
                    ""
                  else
                    "echo 'FAIL: export ExecStart lost config or extra argument boundaries'; exit 1"
                }

                echo "module-eval: checking external-config import ExecStart"
                ${
                  if externalImportExecOk then
                    ""
                  else
                    "echo 'FAIL: import ExecStart lost config or extra argument boundaries'; exit 1"
                }

                echo "module-eval: checking rendered TOML against packaged CLI loader"
                config_file=$(echo '${importService.serviceConfig.ExecStart}' | sed 's/.*"--config" "\([^"]*\)".*/\1/')
                if traktor-m3u-sync export --format itunes --config "$config_file" > loader.out 2>&1; then
                  echo 'FAIL: packaged CLI unexpectedly succeeded without the fixture store'
                  exit 1
                fi
                case "$(< loader.out)" in
                  *'ERROR code=config_error'*)
                    echo 'FAIL: generated M3U-to-iTunes config was rejected by the loader'
                    exit 1
                    ;;
                esac

                echo "module-eval: all checks passed" > $out
              '';
          };

          packages = {
            default = traktor-m3u-sync;
            traktor-m3u-sync = traktor-m3u-sync;
            traktor-nml-utils = traktor-nml-utils;
          };

          apps = {
            default = {
              type = "app";
              program = pkgs.lib.getExe traktor-m3u-sync;
            };
          };

          devShells.default = pkgs.mkShell {
            packages = with pkgs; [
              git
              just
              lefthook
              python314
              pyright
              ruff
              treefmt
              uv
            ];

            env = {
              # UV_PYTHON = "${pkgs.python314}/bin/python3.14";
            };

            shellHook = ''
              unset PYTHONPATH
            '';
          };
        };
    };
}
