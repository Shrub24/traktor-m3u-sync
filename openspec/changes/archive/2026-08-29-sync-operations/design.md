## Context

Exports are store-mediated and format-specific. NML export already protects its mutable source with backup, reload validation, and restore; M3U and iTunes write generated targets directly. The two NixOS oneshots intentionally leave execution policy to downstream systemd configuration.

## Goals / Non-Goals

**Goals:**
- Prevent partial M3U and iTunes output from replacing a prior complete target.
- Let operators exercise export behavior without changing configured targets or the store.
- Let automation opt into a distinct completed-with-warnings result without breaking existing callers.

**Non-Goals:**
- Import dry run, JSON report files, rolling backup retention, target-directory transactions, scheduling/chaining units, or changing default warning exit behavior.

## Decisions

### D1: Atomically replace each generated target

M3U files and the iTunes XML file are written to a temporary sibling, then replaced with `os.replace()` only after successful serialization. Temporary files are removed on failure. Existing target modes are retained; new targets receive an ordinary umask-derived file mode rather than the temporary file's owner-only mode. This prevents a truncated or unexpectedly private output file without introducing NML-style backup accumulation for generated, disposable targets. M3U's playlist files remain independently atomic; an all-or-nothing directory transaction is deferred.

### D2: Reuse exporters for export-only dry runs

The service validates the normal command path through a non-creating read-only store access, then supplies an isolated temporary target to the existing exporter: a temporary directory for M3U, a temporary XML path for iTunes, and a temporary copy of the NML collection for NML. It reports the normal warnings and counts, removes temporary output, and never changes the configured target or store. An absent store fails without creating its database or parent directory. Reusing real serialization avoids a divergent preview implementation.

### D3: Warning failure is explicit and distinct

`--fail-on-warning` retains normal output but returns exit status `2` when a command otherwise completes with one or more warnings. Failures remain status `1`; successful commands without this flag remain status `0`, including warnings. This preserves compatibility while giving downstream systemd units an intentional strict mode.

### D4: Keep operational policy outside the module

The NixOS module receives no timer, path unit, combined worker, or implicit strictness change. It exposes explicit `export.extraArgs` and `import.extraArgs` seams, appended to the respective oneshot command, so operators can opt into flags such as `--fail-on-warning` through downstream policy. Each generated `ExecStart` is constructed as one raw argument list (executable, subcommand, format, config path, extra arguments) and escaped once to preserve valid external config paths and argument boundaries.

## Risks / Trade-offs

- [A process or host failure can still leave a temporary sibling] → names are unique and cleanup runs on ordinary exceptions; the prior target remains intact.
- [M3U export can complete only partly across many playlists] → each file is protected individually; whole-directory publication is a separate, higher-complexity capability.
- [NML dry run spends time copying and rewriting a temporary collection] → it is intentionally a safety rehearsal, not a zero-cost status command.
- [Warning strictness is opt-in] → existing callers are stable; downstream automation must explicitly select the desired policy.

## Migration Plan

Existing commands and module services retain their behavior. Operators that want warning-sensitive automation add `--fail-on-warning` through their existing downstream service arguments. No config migration or database migration is required.
