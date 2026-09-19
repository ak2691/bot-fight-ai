# LLM generation and improvement plan

## Generation contract

The model is an untrusted candidate generator. The prompt should include only the match context needed for the decision and should identify the exact schema, rules version, ability definitions, node/resource limits, previous telemetry, and opponent observations. The model must return a JSON document matching the program schema; explanations belong outside the candidate payload or are discarded.

The initial candidate count should be configurable and small, normally 10–20. Candidate diversity can be encouraged through prompt parameters or controlled sampling, but every result must still pass the same validator and simulator.

## Model adapter boundary

Keep the AI service independent of a particular provider. A future adapter should support:

- A development/mock generator for deterministic tests.
- A hosted model during early experimentation if needed.
- An open-weight, self-hosted model through vLLM or a compatible JSON-serving endpoint.
- Model, tokenizer, prompt-template, decoding, and schema versions recorded per request.

The live decision path must have a fallback policy for model timeout or malformed output. The policy may choose a previously validated program or a scripted safe strategy, but it must be explicit and tested.

## Experiment record and training example

Store at least:

- Match context and prior-round telemetry.
- Prompt/template version and normalized LLM input.
- Raw model output and parsed candidates.
- Candidate validation issues.
- Simulation request, seeds, opponent pool, simulator/rules versions, and per-scenario results.
- Selected candidate and ranking rationale.
- Submitted program and API result.
- Eventual real-match outcome and telemetry.

Training examples should be constructed offline from replayable records. Possible targets include a complete successful program, a program edit, a preferred candidate over a rejected/weaker candidate, or a round-aware modification. Do not treat a high simulated score as ground truth unless the simulator version and rules snapshot are retained.

## Version lifecycle

Model artifacts are immutable and named explicitly, for example `BotFightAI-v1` and `BotFightAI-v2`. A candidate model is evaluated against a frozen suite containing:

- Scripted and baseline opponent programs.
- Previous promoted AI versions.
- Fixed seeds and representative rules/ability snapshots.
- Adversarial validation cases and malformed-output cases.

Promote a new model only when it passes validity, reproducibility, regression, and performance gates against the previous promoted version. Keep the model version used by each live decision forever in experiment data.

## Deliberate non-goal for v1

Do not add a neural network to approximate simulator outcomes in the first version. Direct simulation is authoritative; a learned evaluator is a later performance optimization only after profiling shows that simulation throughput is the actual bottleneck.
