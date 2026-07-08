{
  description = "Nix-first workspace for traktor-m3u-sync";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    treefmt-nix.url = "github:numtide/treefmt-nix";
  };

  outputs =
    inputs@{
      self,
      flake-parts,
      treefmt-nix,
      ...
    }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      perSystem =
        { pkgs, system, ... }:
        let
          treefmtEval = treefmt-nix.lib.evalModule pkgs ./treefmt.nix;
        in
        {
          formatter = treefmtEval.config.build.wrapper;

          checks.formatting = treefmtEval.config.build.check self;

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

            env.UV_PYTHON = "${pkgs.python314}/bin/python3.14";

            shellHook = ''
              echo "Loaded traktor-m3u-sync dev shell (${system})"
            '';
          };
        };
    };
}
