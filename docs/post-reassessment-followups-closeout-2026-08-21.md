# CFR post–Travel Stack Reassessment follow-ups — closeout (2026-08-21)

State: **complete**.

This is the Orchestrator-level durable checkpoint for the accepted SR-B → SR-F follow-up sequence. It does not activate FTR work or broaden current runtime geography.

## Resolved packages

- **SR-B — PASS.** `gflights==0.3.1` is the qualified current Google access adapter after a bounded same-basket comparison. It remains replaceable and fail-closed. Evidence: `docs/gflights-qualification-2026-08-21.md`.
- **SR-C — PASS / KEEP-ADAPT.** No currently authorized TWD-0 substrate qualified for destination-free discovery over an arbitrary supplied availability window, so the bounded Scoped planner remains temporary implementation ADAPT rather than Product Intent. Evidence: `docs/scoped-native-window-bakeoff-2026-08-21.md`.
- **SR-D — PASS.** Official Kiwi.com remote MCP is qualified and integrated only as the independent known-route exact/flexible fallback after gflights technical failure. Destination-free anomaly discovery and open-jaw remain gflights-only. Evidence: `docs/executable-redundancy-qualification-2026-08-21.md`.
- **SR-E — PASS.** Typed access-blind-spot evidence distinguishes restricted surface existence from specific fare existence and never invents inaccessible prices/candidates. Evidence: `docs/access-blind-spots-2026-08-21.md`.
- **SR-F — PASS.** The fixed-watch crawler/cadence/state/parser subsystem and Scrapy/Playwright execution plane are retired. Generic public-Web/social Signal provenance/dedupe and verification-only semantics remain. Evidence: `docs/public-intelligence-simplification-2026-08-21.md`.

## Resulting architecture

CFR owns product truth, orchestration, anomaly/absolute-low semantics, coverage/freshness/fail-closed behavior, immutable evidence, TWD-0 policy, and the CFR→FTR producer contract. Commodity airfare access remains replaceable: destination-free anomaly acquisition uses qualified gflights; known-route exact/flexible completion uses gflights with bounded Kiwi MCP fallback; open-jaw remains gflights-only. Query/Scoped Mode keeps the current bounded planner until a true native-window BORROW substrate qualifies. Public Web/social intelligence is opportunistic/verification-only and is not backend coverage or Deal authority. Restricted-access blind spots are typed evidence rather than inferred fares.

Current implemented geography remains the existing Asia/Oceania runtime filter. The accepted worldwide substrate-native direction remains future capability and is not activated by this workstream.

No FTR implementation work was started by SR-B through SR-F.
