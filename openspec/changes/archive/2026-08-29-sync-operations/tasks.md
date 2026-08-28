## 1. Safe generated-output publication

- [x] 1.1 Add a standard-library same-directory atomic-write helper and route M3U and iTunes export targets through it; verify a write failure leaves a pre-existing target byte-for-byte unchanged.
- [x] 1.2 Add regression coverage for successful atomic replacement, target-mode preservation, and temporary-file cleanup for both M3U and iTunes outputs.

## 2. Export rehearsal

- [x] 2.1 Add `--dry-run` CLI and service wiring; verify dry runs preserve normal summaries/warnings, do not change the store, and do not create an absent store.
- [x] 2.2 Run M3U and iTunes exporters against isolated temporary targets for dry runs; verify configured targets remain unchanged.
- [x] 2.3 Run NML dry runs against a temporary collection copy; verify the configured collection remains byte-for-byte unchanged while the sandbox write path is exercised.

## 3. Warning-sensitive automation

- [x] 3.1 Add `--fail-on-warning` with distinct status `2` after otherwise successful warning-producing imports and exports; verify default warning behavior remains status `0` and real failures remain status `1`.

## 4. Documentation and validation

- [x] 4.1 Document the new operational flags and downstream-systemd usage boundary; verify README and Nix deployment guidance are consistent.
- [x] 4.2 Expose explicit NixOS import/export `extraArgs` options and append them to safely escaped full oneshot argument lists; verify module evaluation covers both directions and an external config path with spaces.
- [x] 4.3 Run full validation (`nix develop -c bash -lc 'uv sync --dev >/dev/null && just check'`, `nix flake check`, and `openspec validate sync-operations --type change --strict`).
