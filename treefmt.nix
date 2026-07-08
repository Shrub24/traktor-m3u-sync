{ pkgs, ... }:
{
  projectRootFile = "flake.nix";

  programs.nixfmt.enable = true;
  programs.ruff-check.enable = true;
  programs.ruff-format.enable = true;

  settings.global.excludes = [
    ".git/**"
    ".jj/**"
    "openspec/changes/archive/**"
  ];
}
