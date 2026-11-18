# Tasks: engine-analysis-lifecycle

## 1. Implementation

- [x] 1.1 `engine-analysis` command over a read-only managed-subtree analysis check
- [x] 1.2 `engine-analysis-guest` package with the request/quit protocol
- [x] 1.3 Guest task answers Engine's prompts through UI Automation (quit confirmation verified live; notices from a UIA dump)

## 2. Validation

- [x] 2.1 Tests: saved-grid rule, managed-subtree scope, read-only, busy exit code, flag/config handling
- [ ] 2.2 Live: guest task starts and closes Engine in the headless VM; command observes saved analysis while Engine is open

## 3. Docs

- [x] 3.1 README, ARCHITECTURE and PLAN
