# Working on Giethoorn

- This is an early public market-data foundation. Do not infer trading readiness.
- Read README.md and docs/status.md before changing behavior.
- Use the existing checkout; cloud tasks are isolated. Do not create a worktree
  unless the user requests one.
- Run ./scripts/check for Rust changes. It includes real local WebSocket tests;
  no exchange access or credentials are required.
- Keep engine transitions pure and replayable. Never read clocks or randomness in
  the engine. Use exact decimals for prices, sizes and financial calculations.
- Persist incoming events before processing and outgoing intents before sending.
  Recording failures are terminal. Do not silently skip corrupt journal records.
- Keep keys, credentials and recordings out of tracked files. Do not weaken TLS.
- Changing the event schema or deterministic output requires an explicit version
  decision and fixture/test updates. Never relabel synthetic fixtures as live data.
