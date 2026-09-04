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

      imports = [ treefmt-nix.flakeModule ];

      flake = {
        nixosModules.traktor-m3u-sync = import ./nix/modules/traktor-m3u-sync.nix;
        nixosModules.default = self.nixosModules.traktor-m3u-sync;
      };

      perSystem =
        {
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
            doCheck = false;
            meta = {
              description = "Traktor NML to M3U playlist sync tool";
              homepage = "https://github.com/wolkenarchitekt/traktor-m3u-sync";
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
                      fileSystems."/" = {
                        device = "/dev/null";
                        fsType = "ext4";
                      };
                      boot.loader.grub.devices = [ "nodev" ];

                      services.traktor-m3u-sync = {
                        enable = true;
                        package = traktor-m3u-sync;
                        supplementaryGroups = [ "media" ];
                        states.library.path = "/var/lib/playlist-sync/library.db";
                        jobs = {
                          ingest = {
                            action = "import";
                            state = "library";
                            format = "m3u";
                            m3u = {
                              library_root = "/mnt/music";
                              import_dir = "/mnt/playlists/import";
                            };
                            onSuccess = [
                              "itunes"
                              "engine"
                            ];
                            extraArgs = [ "--fail-on-warning" ];
                          };
                          itunes = {
                            action = "export";
                            state = "library";
                            format = "itunes";
                            itunes = {
                              output_file = "/mnt/playlists/iTunes Music Library.xml";
                              location_base = "file://localhost/M:/Music";
                            };
                            onFailure = [ "engine" ];
                          };
                          engine = {
                            action = "export";
                            state = "library";
                            format = "engine";
                            engine = {
                              database_path = "/mnt/engine/Engine Library/Database2/m.db";
                              track_path_prefix = "../Music";
                              managed_root = "Managed Engine Playlists";
                            };
                            extraArgs = [ "--dry-run" ];
                          };
                          external = {
                            action = "export";
                            state = "library";
                            format = "m3u";
                            configFile = "/etc/playlist-sync/config with % percent.toml";
                          };
                          reporting = {
                            action = "export";
                            state = "library";
                            format = "m3u";
                            m3u = {
                              library_root = "/mnt/music";
                              output_dir = "/mnt/playlists/report-out";
                            };
                            reportFile = "/var/lib/playlist-sync/reports/last run.json";
                          };
                        };
                      };
                    }
                  ];
                };

                cfg = evaled.config.services.traktor-m3u-sync;
                services = evaled.config.systemd.services;
                ingest = services."traktor-m3u-sync-import@ingest";
                itunes = services."traktor-m3u-sync-export@itunes";
                engine = services."traktor-m3u-sync-export@engine";
                external = services."traktor-m3u-sync-export@external";
                reporting = services."traktor-m3u-sync-export@reporting";
                importTemplate = services."traktor-m3u-sync-import@";
                exportTemplate = services."traktor-m3u-sync-export@";
                legacyAbsent =
                  !(builtins.hasAttr "store" cfg)
                  && !(builtins.hasAttr "import" cfg)
                  && !(builtins.hasAttr "export" cfg);
                # Force assertion booleans first and only interpolate messages of
                # failures: merged base assertions (e.g. filesystems) have messages
                # that crash on minimal fixtures, same shape as NixOS top-level.
                failedModuleMessages = nixpkgs.lib.concatMap (
                  assertion:
                  if assertion.assertion || !nixpkgs.lib.hasPrefix "services.traktor-m3u-sync" assertion.message then
                    [ ]
                  else
                    [ assertion.message ]
                ) evaled.config.assertions;
                negativeFixture = nixpkgs.lib.nixosSystem {
                  inherit (pkgs) system;
                  modules = [
                    self.nixosModules.traktor-m3u-sync
                    {
                      services.traktor-m3u-sync = {
                        enable = true;
                        package = traktor-m3u-sync;
                        states = {
                          one.path = "/var/lib/playlist-sync/one.db";
                          two.path = "/var/lib/playlist-sync/one.db";
                        };
                        jobs = {
                          cycleA = {
                            action = "import";
                            state = "one";
                            format = "m3u";
                            m3u = {
                              library_root = "/mnt/music";
                              import_dir = "/mnt/playlists/import";
                            };
                            onSuccess = [ "cycleB" ];
                            onFailure = [ "ghost" ];
                          };
                          cycleB = {
                            action = "export";
                            state = "one";
                            format = "m3u";
                            m3u = {
                              library_root = "/mnt/music";
                              output_dir = "/mnt/playlists/out";
                            };
                            onSuccess = [ "cycleA" ];
                          };
                          dupImport = {
                            action = "import";
                            state = "one";
                            format = "m3u";
                            m3u = {
                              library_root = "/mnt/music";
                              import_dir = "/mnt/playlists/import";
                            };
                          };
                          externalOverlap = {
                            action = "export";
                            state = "two";
                            format = "itunes";
                            configFile = "/etc/playlist-sync/config.toml";
                            itunes.output_file = "/tmp/overlap.xml";
                          };
                        };
                      };
                    }
                  ];
                };
                negativeMessages = nixpkgs.lib.concatMap (
                  assertion:
                  if assertion.assertion || !nixpkgs.lib.hasPrefix "services.traktor-m3u-sync" assertion.message then
                    [ ]
                  else
                    [ assertion.message ]
                ) negativeFixture.config.assertions;
                expectedNegativeMessages = [
                  "services.traktor-m3u-sync.states must use distinct store paths."
                  "services.traktor-m3u-sync.states allow at most one import job per state."
                  "services.traktor-m3u-sync.jobs.cycleA.onSuccess reaches a cycle."
                  "services.traktor-m3u-sync.jobs.cycleA.onFailure references a missing job."
                  "services.traktor-m3u-sync.jobs.cycleB.onSuccess reaches a cycle."
                  "services.traktor-m3u-sync.jobs.externalOverlap.configFile cannot be combined with selected-format generated settings."
                ];
                negativeOk =
                  nixpkgs.lib.all (msg: builtins.elem msg negativeMessages) expectedNegativeMessages
                  && negativeMessages == expectedNegativeMessages;
                identityOk =
                  importTemplate.serviceConfig.User == "playlist-sync"
                  && exportTemplate.serviceConfig.Group == "playlist-sync"
                  && importTemplate.serviceConfig.SupplementaryGroups == [ "media" ];
                fanOutOk =
                  ingest.unitConfig.OnSuccess == [
                    "traktor-m3u-sync-export@itunes.service"
                    "traktor-m3u-sync-export@engine.service"
                  ]
                  &&
                    itunes.unitConfig.OnFailure == [
                      "traktor-m3u-sync-export@engine.service"
                    ];
                execOk =
                  builtins.match ".*\"import\" \"--format\" \"m3u\" \"--config\" .* \"--fail-on-warning\"" (
                    builtins.elemAt ingest.serviceConfig.ExecStart 1
                  ) != null
                  &&
                    builtins.match ".*\"export\" \"--format\" \"engine\" \"--config\" .* \"--dry-run\"" (
                      builtins.elemAt engine.serviceConfig.ExecStart 1
                    ) != null
                  &&
                    builtins.match ".*\"export\" \"--format\" \"m3u\" \"--config\" \"/etc/playlist-sync/config with %% percent.toml\"" (
                      builtins.elemAt external.serviceConfig.ExecStart 1
                    ) != null;
                reportOk =
                  builtins.match ".*\"--report-file\" \"/var/lib/playlist-sync/reports/last run.json\"" (
                    builtins.elemAt reporting.serviceConfig.ExecStart 1
                  ) != null
                  &&
                    builtins.match ".*\"--report-file\".*" (builtins.elemAt ingest.serviceConfig.ExecStart 1) == null;
              in
              pkgs.runCommand "module-eval-test" { nativeBuildInputs = [ traktor-m3u-sync ]; } ''
                set -eu
                ${
                  if failedModuleMessages == [ ] then
                    ""
                  else
                    "echo 'FAIL: module assertions: ${nixpkgs.lib.concatStringsSep "; " failedModuleMessages}'; exit 1"
                }
                ${if negativeOk then "" else "echo 'FAIL: negative assertions'; exit 1"}
                ${if identityOk then "" else "echo 'FAIL: shared template identity'; exit 1"}
                ${if fanOutOk then "" else "echo 'FAIL: OnSuccess/OnFailure fan-out'; exit 1"}
                ${if execOk then "" else "echo 'FAIL: escaped job argv'; exit 1"}
                ${if reportOk then "" else "echo 'FAIL: reportFile argv escaping'; exit 1"}

                for config_file in \
                  $(echo '${builtins.elemAt ingest.serviceConfig.ExecStart 1}' | sed 's/.*"--config" "\([^"]*\)".*/\1/') \
                  $(echo '${builtins.elemAt itunes.serviceConfig.ExecStart 1}' | sed 's/.*"--config" "\([^"]*\)".*/\1/') \
                  $(echo '${builtins.elemAt engine.serviceConfig.ExecStart 1}' | sed 's/.*"--config" "\([^"]*\)".*/\1/'); do
                  action=export
                  format=engine
                  case "$config_file" in
                    *ingest*) action=import; format=m3u ;;
                    *itunes*) format=itunes ;;
                  esac
                  if traktor-m3u-sync "$action" --format "$format" --config "$config_file" > loader.out 2>&1; then
                    echo "FAIL: CLI unexpectedly completed fixture job"
                    exit 1
                  fi
                  case "$(< loader.out)" in
                    *'ERROR code=config_error'*)
                      echo "FAIL: packaged CLI rejected generated $format config"
                      exit 1
                      ;;
                  esac
                done

                touch "$out"
              '';
          };

          packages = {
            default = traktor-m3u-sync;
            traktor-m3u-sync = traktor-m3u-sync;
            traktor-nml-utils = traktor-nml-utils;
          };

          apps.default = {
            type = "app";
            program = pkgs.lib.getExe traktor-m3u-sync;
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
