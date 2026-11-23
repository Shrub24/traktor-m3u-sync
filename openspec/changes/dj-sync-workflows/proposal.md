# Make DJ sync an operator-visible workflow

## Why

A successful playlist fetch does not mean exports are ready. The current deployment chains independent systemd jobs, so the operator has to reconcile a successful fetch, a pending Engine analysis run, and possibly an old USB build failure. A single build can also publish Engine successfully while Pioneer fails. The unit results alone do not say what is usable or what to retry.

## What changes

- Prepare exports automatically on the host after playlist sync. Add a Linux **Sync Manager** TUI for reviewing and delivering to a selected stick. Keep the existing standalone commands and generic NixOS import/export jobs.
- Give each run one versioned report shared by the terminal and future clients. Report the current stage, elapsed time, measured progress, and outcomes by format, with an actionable next step on failure.
- Retry only work whose inputs and safety checks still hold. Keep successful formats and the last verified generation of any failed format.
- Measure a cold refresh, a warm no-op, and a one-track update before changing performance-sensitive behavior.

## Scope

This proposal covers the application workflow, Linux TUI, and the downstream composition needed to exercise it. A private mobile web UI is a follow-up. It does not add device discovery, a daemon or queue, a new authoritative store, or Pioneer edit import. It does not change cue mapping, database replacement approvals, or the publication guarantees of either USB format.
