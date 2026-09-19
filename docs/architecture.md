# Architecture

This is a proposed target architecture, not a confirmed repository layout. The simulator and shared-contract artifacts are intentionally not scaffolded yet.

## System shape

Bot Fight AI is an independent backend. Bot Fight Online remains responsible for live-match authority, player/account state, build-phase timing, and accepting the final program. The AI service performs planning and experimentation outside the game server.

```text
                         match context / round telemetry
        +------------------------------+------------------------------+
        |                                                             |
        v                                                             |
+--------------------+       candidates       +----------------------+ |
| Bot Fight Online   | ----------------------> | Bot Fight AI        | |
| live game + API    | <---------------------- | Python/FastAPI      | |
+--------------------+    selected program    | orchestration       | |
                                                +----------+-----------+ |
                                                           |             |
                                         batch simulations |             |
                                                           v             |
                                                +----------------------+ |
                                                | Simulation service   | |
                                                | Java REST            | |
                                                +----------+-----------+ |
                                                           | typed calls |
                                                           v             |
                                                +----------------------+ |
                                                | Simulation engine    | |
                                                | pure Java, headless  | |
                                                +----------+-----------+ |
                                                           |             |
                                                           v             |
                                                match results/telemetry |
                                                                         |
                         experiment data / real result callback         |
                                                +----------------------+ |
                                                | AI PostgreSQL         |<+
                                                +----------------------+  |
                                                                          |
                                                +----------------------+  |
                                                | LLM runtime/training |--+
                                                +----------------------+
```

The arrows are logical data flow, not a requirement that every component be deployed in the same network or process.

## Component responsibilities

### Bot Fight Online

- Own live match state, player-selected abilities, build-phase deadlines, and authoritative rules.
- Provide a versioned match-context endpoint and a versioned program-submission endpoint.
- Optionally provide previous-round telemetry and the opponent behavior observables permitted by the game.
- Return or reference the exact rules/ability snapshot used by the match so simulations do not run against a moving definition.

### `ai-service`

- Accept and normalize match context.
- Build a versioned LLM request containing rules, selected abilities, opponent information, and prior telemetry.
- Request a configurable candidate count, initially 10–20.
- Parse strict JSON, validate the schema, then run semantic validation against the supplied rules and abilities.
- Build an opponent pool and send a batch of candidate/opponent/seed scenarios to the simulation service.
- Rank candidates primarily by simulator outcomes, with deterministic tie-breakers and explicit safety/validity rules.
- Persist the complete experiment and submit the selected program through Bot Fight Online’s API.
- Record the real match result and feedback for later dataset construction.

### Proposed future simulation engine

- Contain the extracted deterministic game model and match loop.
- Accept typed, self-contained inputs: rules snapshot, match configuration, two programs, and seed.
- Produce typed result summaries and telemetry suitable for replay and aggregation.
- Be usable from unit tests and batch callers without starting a server.

### Proposed future simulation service

- Expose a versioned batch simulation endpoint.
- Authenticate callers, enforce payload and resource limits, deserialize contracts, invoke the engine, and serialize results.
- Isolate per-scenario failures where possible and return correlation IDs.
- Never become the source of truth for game rules; it is an adapter around the engine.

### Experiment storage and training

- Store immutable context, prompts, raw model outputs, normalized candidates, validation issues, simulation inputs/results, selection rationale, model version, simulator/rules versions, and real-match feedback.
- Build training examples offline from replayable records.
- Keep training and model promotion out of the live match-critical path.

## Dependency direction

```text
future shared contracts  <-  simulation service  ->  simulation engine
future shared contracts  <-  AI service           ->  Bot Fight Online API
                                                    ->  LLM runtime
                                                    ->  AI experiment database
```

The engine must not depend upward on the service, AI application, database, or production website. If a type is needed by both HTTP and engine code, define a stable contract/domain mapping rather than importing a web framework into the engine.

## Runtime sequence

1. Bot Fight Online sends the AI a context snapshot for a match and round.
2. The AI records the snapshot and builds an LLM request.
3. The LLM returns structured candidate programs.
4. The AI performs the confirmed structured-format and game-rule validation; invalid candidates are retained as rejected experiment data.
5. The AI expands valid candidates across an opponent pool and explicit seeds.
6. The simulation service runs the batch using the requested simulator/rules versions.
7. The AI aggregates results, selects a candidate, records the decision, and submits it before the deadline.
8. Bot Fight Online later sends the real result and telemetry; the AI stores it as feedback.

## Deployment intent

The AI workload and simulation workload should be deployable separately from production Bot Fight Online. A later Docker deployment may contain distinct containers for the Python service, Java simulation service, AI PostgreSQL, and model runtime. The initial scaffold does not choose a cloud, orchestration platform, model size, or GPU topology.
