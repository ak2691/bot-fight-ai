# Requirements and phased scope

## Functional requirements

| ID | Requirement | Initial acceptance signal |
| --- | --- | --- |
| F-01 | Receive match context | A versioned request can carry round, selected abilities, opponent abilities, rules/ability definitions, and prior telemetry when available. |
| F-02 | Generate candidates | An LLM adapter can request a bounded candidate set, normally 10–20, and returns JSON only. |
| F-03 | Validate candidates | The confirmed structured format, AST/graph, ability-reference, value-range, reachability, node-limit, and game-rule checks produce machine-readable issues. |
| F-04 | Simulate candidates | A confirmed simulator service accepts batch scenarios containing programs, match configuration, and seeds and returns per-scenario outcomes and telemetry. |
| F-05 | Select a program | Ranking is primarily based on simulator performance and has deterministic tie-breaking plus a clear minimum-validity policy. |
| F-06 | Submit a program | The AI calls a versioned Bot Fight Online API with an idempotency key before the build phase deadline. |
| F-07 | Persist experiments | A record can reconstruct the context, prompt, model output, candidate, validation, simulation, selection, and live result. |
| F-08 | Adapt across rounds | Prior telemetry and observed behavior are included in the next-round decision context when available. |
| F-09 | Improve models offline | Reproducible examples can be built from stored experiments, and immutable model versions can be evaluated and promoted. |

## Non-functional requirements

- **Determinism:** same simulator version, rules snapshot, inputs, and seed produce the same result.
- **Isolation:** simulation has no rendering, WebSockets, database calls, network calls, wall-clock sleeps, or real-time loop dependencies.
- **Reproducibility:** every decision records schema, game rules, simulator, model, prompt, seed, and opponent-pool versions.
- **Safety:** untrusted LLM output is treated as data; validate size, depth, references, values, and resource cost before execution.
- **Availability:** a failed candidate or opponent scenario should not discard unrelated batch results; API timeouts and retry behavior are explicit.
- **Observability:** correlation IDs, candidate IDs, scenario IDs, validation counts, simulation duration, and failure reasons are measurable without logging secrets.
- **Compatibility:** breaking contract changes use a new version; rules and simulator changes are visible in result metadata.
- **Performance:** benchmark batch throughput and build-phase end-to-end latency before adding optimizations or a learned evaluator.
- **Security:** authenticate service-to-service calls, authorize program submission, protect model/database credentials, and minimize retained human data.

## First implementation scope

The first working slice should be deliberately narrow:

1. Confirm where the simulator and shared contracts will live.
2. Obtain one canonical rules/program snapshot from Bot Fight Online.
3. Build the simulator with deterministic replay fixtures and a batch endpoint in the confirmed location.
4. Implement a Python orchestration path with a replaceable LLM adapter and strict candidate validation.
5. Add a small scripted opponent pool and self-play.
6. Add experiment persistence sufficient to replay a decision.

## Explicitly deferred

- A neural-network candidate evaluator or learned surrogate score.
- Fine-tuning, online reinforcement learning, and automatic model promotion.
- Historical human-strategy ingestion until privacy, consent, and data retention are defined.
- Distributed simulation scheduling, GPU autoscaling, and speculative execution.
- Recreating the website’s rendering, WebSocket protocol, database schema, or live-clock loop.

## Acceptance criteria for the architecture scaffold

- A future contributor can identify the responsibility and dependency boundary of every top-level directory.
- Proposed component responsibilities are documented without treating unconfirmed folders or APIs as implemented.
- The eventual service envelopes and versioning policy are selected only after the external game setup is confirmed.
- Unknown game-specific details are visible as open questions rather than silently fixed in the scaffold.
