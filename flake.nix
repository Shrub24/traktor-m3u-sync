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
                        library = {
                          traktor_root = "/mnt/traktor";
                          m3u_root = "/mnt/music";
                        };
                        store.path = "/var/lib/traktor-m3u-sync/store.db";
                        nml = {
                          collection_path = "/mnt/traktor/collection.nml";
                          sandbox_name = "Imported Playlists";
                        };
                        m3u = {
                          output_dir = "/mnt/playlists/export";
                          import_dir = "/mnt/playlists/import";
                        };
                        itunes = {
                          output_file = "/mnt/playlists/iTunes Music Library.xml";
                          base_path = "/mnt/music";
                        };
                        export = {
                          enable = true;
                          format = "itunes";
                        };
                        import = {
                          enable = true;
                          format = "nml";
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

                cfg = evaled.config.services.traktor-m3u-sync;

                exportService = evaled.config.systemd.services.traktor-m3u-sync-export;
                importService = evaled.config.systemd.services.traktor-m3u-sync-import;
                externalExportService = externalConfigEvaled.config.systemd.services.traktor-m3u-sync-export;
                externalImportService = externalConfigEvaled.config.systemd.services.traktor-m3u-sync-import;

                # Smoke-test: verify the module option surface exists and
                # evaluates without error, the service ExecStart lines pass
                # their declared --format and --config, and the generated
                # TOML parses with every section and field the CLI loader
                # requires.
                moduleSurfaceOk = cfg.enable == true;
                exportExecOk =
                  builtins.match ".*\"export\" \"--format\" \"itunes\" \"--config\" .*" exportService.serviceConfig.ExecStart
                  != null;
                importExecOk =
                  builtins.match ".*\"import\" \"--format\" \"nml\" \"--config\" .*" importService.serviceConfig.ExecStart
                  != null;
                externalExportExecOk =
                  builtins.match ".*\"export\" \"--format\" \"m3u\" \"--config\" \"/etc/traktor-m3u-sync/config with %% percent.toml\" \"--fail-on-warning\"" externalExportService.serviceConfig.ExecStart
                  != null;
                externalImportExecOk =
                  builtins.match ".*\"import\" \"--format\" \"m3u\" \"--config\" \"/etc/traktor-m3u-sync/config with %% percent.toml\" \"--fail-on-warning\"" externalImportService.serviceConfig.ExecStart
                  != null;
              in
              pkgs.runCommand "module-eval-test" { nativeBuildInputs = [ python ]; } ''
                set -e

                echo "module-eval: checking option surface"
                ${if moduleSurfaceOk then "" else "echo 'FAIL: enable option not true'; exit 1"}

                echo "module-eval: checking export service ExecStart"
                ${if exportExecOk then "" else "echo 'FAIL: export ExecStart missing expected arguments'; exit 1"}

                echo "module-eval: checking import service ExecStart"
                ${if importExecOk then "" else "echo 'FAIL: import ExecStart missing expected pattern'; exit 1"}

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

                echo "module-eval: checking rendered TOML against loader requirements"
                config_file=$(echo '${importService.serviceConfig.ExecStart}' | sed 's/.*"--config" "\([^"]*\)".*/\1/')
                python - "$config_file" <<'EOF'
                import sys
                import tomllib

                with open(sys.argv[1], "rb") as fh:
                    raw = tomllib.load(fh)

                assert all(t in raw for t in ("library", "store", "nml", "m3u", "itunes")), raw
                assert raw["library"]["traktor_root"] == "/mnt/traktor"
                assert raw["library"]["m3u_root"] == "/mnt/music"
                assert raw["store"]["path"] == "/var/lib/traktor-m3u-sync/store.db"
                assert raw["nml"]["collection_path"] == "/mnt/traktor/collection.nml"
                assert raw["nml"]["sandbox_name"] == "Imported Playlists"
                assert raw["m3u"]["output_dir"] == "/mnt/playlists/export"
                assert raw["m3u"]["import_dir"] == "/mnt/playlists/import"
                assert raw["itunes"]["output_file"] == "/mnt/playlists/iTunes Music Library.xml"
                assert raw["itunes"]["base_path"] == "/mnt/music"
                EOF

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
