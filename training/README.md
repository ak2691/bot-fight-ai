# Bot Fight model training workspace

This directory is for offline model improvement. It is deliberately separate
from `ai-service`, which remains responsible for live generation, validation,
simulation, and selection.

## The model is not overwritten

The Ollama model currently used by the service (`qwen3:4b`) is a quantized
inference artifact. A QLoRA run should start from the original Hugging Face
checkpoint, not from the Ollama blob:

```text
read-only base checkpoint
        + LoRA adapter learned by one training run
        = adapted model used for evaluation
```

For this machine, the Ollama metadata identifies the current model family as
`Qwen/Qwen3-4B-Thinking-2507`. Verify the exact upstream revision before the
first download and record that revision in the run manifest.

Each run should get a new immutable directory, for example. The training
launcher or run wrapper should write the `run-manifest.json` with the exact
base revision, dataset manifest hash, prompt/rules versions, and trainer
versions before marking the run complete.

```text
training/runs/BotFightAI-v0.1/
  adapter_model.safetensors
  adapter_config.json
  tokenizer files and trainer state
  run-manifest.json
```

The base model is never edited. A later run starts from the same base plus the
chosen adapter, or from a separately named promoted model if that is an
intentional decision. Do not train over an existing run directory.

## LoRA and QLoRA

LoRA freezes the base weights and learns small low-rank matrices attached to
selected layers. QLoRA additionally loads the frozen base in 4-bit form while
keeping the LoRA matrices trainable. The adapter is therefore small and the
base model remains reusable. The first experiment should use supervised
fine-tuning (SFT) with QLoRA on the 4B model because this workstation has an
8 GB RTX 4060 Laptop GPU.

Training and serving are different formats:

1. Load the original Transformers checkpoint with 4-bit quantization.
2. Train only the LoRA adapter on accepted Bot Fight demonstrations.
3. Evaluate the base plus adapter against a frozen simulator suite.
4. Keep the adapter as the primary versioned artifact.
5. If it passes promotion gates, optionally merge it into a new full
   Transformers checkpoint. Never merge into the original checkpoint.
6. If Ollama remains the serving runtime, create a new Ollama model tag from
   the merged model, such as `botfight-qwen3-4b-sft-v0.1`; leave `qwen3:4b`
   available as the baseline.

The service must record the exact base model, adapter/run ID, prompt version,
rules snapshot, brain schema, simulator version, and decoding settings for
every decision. A trained adapter is not a replacement for authoritative
validation or simulation.

## Training data contract

The raw JSONL input to `tools/prepare_sft_dataset.py` has one record per
demonstration:

```json
{
  "example_id": "duel-0042-round-1-solution",
  "split": "train",
  "source": "human",
  "messages": [
    {"role": "system", "content": "the exact production system prompt"},
    {"role": "user", "content": "the exact normalized match prompt"},
    {
      "role": "assistant",
      "content": "{\"candidates\":[{\"candidate_id\":\"solution-0042\",\"program\":{}}]}"
    }
  ],
  "quality": {
    "authoritative_valid": true,
    "ruleset_version": "duel-v1",
    "brain_schema_version": "bot-logic-tree-v1",
    "validator_version": "record-the-real-version",
    "simulator_version": "record-the-real-version",
    "evaluation": {
      "completed": 20,
      "wins": 16,
      "draws": 2,
      "losses": 2,
      "score": 0.85
    }
  },
  "provenance": {
    "generator": "human|codex|ollama|other",
    "experiment_id": "stable-experiment-id",
    "opponent_pool_version": "stable-pool-id"
  }
}
```

The `messages` must be the same prompt shape used by the live adapter. The
assistant response stays in the production envelope (`{"candidates": [...]}`)
so training does not create a train/serve format mismatch. For the first SFT
run, use one accepted solution candidate per example and test it with
`candidate_count=1`; candidate diversity can be added after the single-program
path is reliable.

Only examples that pass the authoritative Java validator should enter the
accepted dataset. Simulator results and provenance are required metadata even
when the source is a human or Codex-generated program. The preparation tool
removes metadata from the actual trainer file but writes a manifest containing
record counts and hashes. Rejected candidates remain useful experiment data,
but they are not positive SFT targets.

Codex-generated variations follow the same rule: they are suggestions until
the canonical validator and simulator accept them. Do not add a variation
merely because it parses or looks strategically plausible.

Keep train/validation/test splits separated by scenario or match family, not
by random rows from the same match. Otherwise near-identical program variants
can leak into evaluation and make the model look better than it is.

## First local setup

Use a separate environment from `ai-service`. On Windows, native CUDA may
work, but WSL2/Ubuntu is the more repeatable path for the training stack. Do
not install training dependencies into `ai-service/.venv`.

From this directory, after choosing the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Put raw demonstrations in `training/data/raw/botfight_sft_records.jsonl`,
then validate and prepare them:

```powershell
python tools/prepare_sft_dataset.py `
  --input data/raw/botfight_sft_records.jsonl `
  --output-dir data/generated
```

The command writes `train.jsonl`, `validation.jsonl`, `test.jsonl` when those
splits exist, plus `manifest.json`. The LLaMA-Factory config in
`configs/qwen3_4b_qlora_sft.yaml` is intentionally conservative for an 8 GB
GPU. Start with a very small dataset and one epoch to verify the environment
before spending time on a larger run.

The config is a starting point, not a promotion decision. After training,
run the adapter on held-out prompts and then use the authoritative validator
and simulator suite. Compare it with the unchanged Ollama baseline before
creating a new promoted model tag.

## Planned artifact layout

```text
training/
  configs/                    checked-in run configurations
  data/raw/                   source records, ignored by git
  data/generated/             trainer JSONL and manifest, ignored by git
  runs/BotFightAI-v0.1/       adapter/checkpoints, ignored by git
  tools/                      dependency-light dataset tooling
```
