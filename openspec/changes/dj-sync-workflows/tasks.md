## 1. Report and composition

- [ ] 1.1 Add the versioned run report and progress at operation boundaries; render the same data in the CLI.
- [ ] 1.2 Compose refresh through the existing operations and downstream fetch/guest runners; cover analysis skipped, analysis failed, and per-format partial publication.
- [ ] 1.3 Compose guided stick review and delivery, including explicit approvals, stale-approval refusal, cached preview reuse, and reconnect/retry.

## 2. Deployment and validation

- [ ] 2.1 Wire one supervised DJ refresh in homelab, preserving VM exclusion and the independently useful jobs; remove redundant DJ fan-out and document the operator commands.
- [ ] 2.2 Measure cold, unchanged and one-track runs and record phase timings; validate any optimization against the baseline.
- [ ] 2.3 Verify the guided CLI and recovery on test fixtures, then confirm both workflows on the live setup with explicit approval before any stick write.
