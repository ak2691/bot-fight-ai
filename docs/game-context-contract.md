# Game context and authoritative simulation bridge

## Decision

The Bot Fight Online server at `C:\dev\botfight\server` is the current canonical
source for `duel-v1`. Bot Fight AI does not copy or reinterpret its simulation
rules. A local Java bridge compiles against that server, exports prompt knowledge
from its registries, invokes its submission validator, and runs its duel simulator.

This is a development integration. Production integration still requires an
authenticated, bounded, versioned simulator API owned by Bot Fight Online (or a
confirmed extracted pure-Java engine and REST wrapper).

## Prompt knowledge

`tools/sync-game-contracts.ps1` exports the following directly from server code:

- ruleset, brain-schema, and validator versions;
- arena units, bot size, fixed step, base HP/speed, and closing-zone configuration;
- all permanent ability IDs/names and timing/resource definitions;
- normalized phases, hitboxes, movement, effects, events, and spawned entities;
- actions, variables, selectables, comparators, status effects, and limits.

The complete snapshot is stored at
`ai-service/app/data/duel-v1-game-knowledge.json`. The prompt builder filters it
to standard abilities, the bot's selected abilities, and legally known opponent
abilities. Compact prompts include every canonical variable contract and every
legal common/self ability action. Shared action heads use
`action_configuration_templates`, while integer abilities also carry an
`ability_action_contracts` entry so target, movement, and orientation fields
are not confused with the union of all possible ability fields. Repeated
variable fields use `variable_contract_defaults` plus per-variable overrides.
This is still the complete configuration/type metadata, not a hand-written
summary. The model never receives Java source code.

Regenerate after authoritative gameplay changes:

```powershell
.\tools\sync-game-contracts.ps1 -BotFightServerRoot C:\dev\botfight\server
```

The checked-in snapshot records the Bot Fight Git revision and whether tracked
source changes were present during export. It must be reviewed and versioned
with prompt changes; production experiments must retain these identifiers.

## AI contracts

- `ai-service/contracts/v1/match-context.schema.json` defines the internal,
  self-contained input to candidate generation.
- `ai-service/contracts/v1/candidate-response.schema.json` defines the LLM
  response envelope and the recursive program shape.
- `bot-logic-tree-v1` remains the authoritative submitted brain format.
- `duel-v1` remains the authoritative ruleset.

The candidate schema now encodes the configuration fields that are knowable
without a particular ability/variable registry entry: typed custom-variable
initial values and operands, bounded coordinates/angles, paired coordinate
fields, movement-mode fields, target-mode fields, and the per-branch action
array bound. The request-specific schema also restricts ability actions,
built-in boolean operand types, condition metadata, non-standard loadout IDs,
and per-ability action fields to the abilities present in the match. Rules that
depend on candidate-declared custom variables or deeper game semantics remain
enforced by the exported canonical metadata and `BotSubmissionValidationService`.

The development orchestration boundary is `POST /v1/decide`. It accepts the
match metadata, candidate count, and both players' cumulative selected
abilities (including currently known opponent abilities). Bot Fight AI calls
its internal generation, validation, simulation, and ranking components, then
returns one final `program` for `player_a` and `player_b`. Candidate arrays and
ranking details do not cross back to Bot Fight Online.

Only public/allowed opponent observations belong in `opponent.observations` and
`previous_round_telemetry`. They are intentionally opaque until Bot Fight Online
defines the live match-context API and telemetry privacy policy.

## Validation and simulation

`POST /v1/generate` performs fast machine-readable candidate prechecks after
JSON parsing and then validates every program through the authoritative Java
validator in one bounded batch before reporting validity.

Before those checks, the AI adapter performs narrow compatibility repairs for
known model omissions: it derives a missing `bot.selectedAbility*` selector
from an integer ability action, removes target/movement fields unsupported by
the selected integer action, and aligns obvious built-in operand JSON types.
An unrepresentable boolean-variable operand is replaced with an `always`
condition so the candidate can still be evaluated; the normalized result still
passes both validators and the simulator remains authoritative.

`POST /v1/validate` calls `BotSubmissionValidationService.validateForSimulation`
from the live server build. `POST /v1/simulate` validates both brains and then
runs `DuelSimulationService.simulateCompact` with the explicit seed, standard
arena, deterministic spawn positions, and `duel-v1`.

The simulation endpoint runs one scenario and returns its winner and final bot
state. The evaluation endpoint expands candidates across explicit opponents and
seeds, caps the Cartesian product at 200 scenarios, isolates failures, and ranks
candidates by win/draw score with deterministic tie-breaking. Persistent
opponent-pool management and experiment storage remain subsequent work.

The canonical validator rejects more than 300 total conditions, and a valid
300-condition nested tree remains supported. During testing, one malformed model
response caused Jackson to raise `JsonNodeException`; this was not evidence that
a valid 300-node tree exhausts Java's call stack. The bridge contains validator
exceptions per candidate so unrelated candidates continue. General request-size
and JSON parser limits remain appropriate production boundary protections, but
they are separate from the game's 300-condition rule.
