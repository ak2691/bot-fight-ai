# LLM generation and improvement plan

## Generation contract

The model is an untrusted candidate generator. The prompt should include only the match context needed for the decision and should identify the exact schema, rules version, ability definitions, node/resource limits, previous telemetry, and opponent observations. The model must return a JSON document matching the program schema; explanations belong outside the candidate payload or are discarded.

The system prompt intentionally does not prescribe combat strategy. It supplies
the programming grammar, authoritative ability mechanics, and output
constraints only. When more than one candidate is requested, it may ask for
different legal program structures so generation does not collapse onto one
syntax pattern; strategic behavior is supplied by the model's learned weights
and later fine-tuning/evaluation rather than by hand-written tactics.

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

## First local SFT toolchain

The first training slice is isolated under `training/`. It uses supervised
fine-tuning with QLoRA against the original Transformers checkpoint. The
Ollama `qwen3:4b` artifact is for inference and is not the training source;
the base checkpoint remains read-only and every run writes a new adapter
directory. The first run should target the 4B model on the local 8 GB GPU and
keep thinking disabled so the assistant target remains strict JSON.

The raw demonstration contract stores the exact system/user messages, the
assistant's production candidate envelope, authoritative validator metadata,
simulator metadata, evaluation results, and provenance. The preparation tool
only emits the messages consumed by the trainer and writes a hash manifest;
the source metadata stays available for audit and replay. A program generated
by a person, Codex, or the current model is a positive SFT example only after
it passes the canonical validator and has recorded its evaluation context.

The first experiment should train one accepted program per prompt and be
tested through the existing generation path with `candidate_count=1`. After
that path beats the unchanged baseline on a frozen holdout, candidate
diversity and larger candidate envelopes can be added deliberately. Training
remains offline and must not be placed on the build-phase request path.
