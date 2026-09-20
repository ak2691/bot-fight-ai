import com.example.botfight.DTO.match.MatchReplayDTO;
import com.example.botfight.service.submission.BotSubmissionValidationService;
import com.example.botfight.simulation.bots.BotCodeService;
import com.example.botfight.simulation.bots.BotLogicContracts;
import com.example.botfight.simulation.bots.ConditionEvaluationService;
import com.example.botfight.simulation.core.combat.ActionExecutionService;
import com.example.botfight.simulation.core.logic.ConditionResolutionService;
import com.example.botfight.simulation.core.orchestration.DuelSimulationService;
import com.example.botfight.simulation.core.orchestration.DuelSimulationService.DuelArenaRequest;
import com.example.botfight.simulation.core.orchestration.DuelSimulationService.DuelBotRequest;
import com.example.botfight.simulation.core.orchestration.DuelSimulationService.DuelSimulationRequest;
import com.example.botfight.simulation.core.replay.ReplayMappingService;
import com.example.botfight.simulation.core.state.BotStateService;
import com.example.botfight.simulation.ecs.contracts.AbilityContracts;
import com.example.botfight.simulation.gameconfig.Abilities;
import com.example.botfight.simulation.gameconfig.AbilityRegistry;
import com.example.botfight.simulation.gameconfig.ClosingZoneConfig;
import com.example.botfight.simulation.gameconfig.GameConfigCatalog;
import com.example.botfight.simulation.geometry.ArenaUnits;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Local development bridge to the canonical Bot Fight server implementation.
 * It deliberately contains no game rules. All rules, validation, hitboxes, and
 * simulation behavior are read from or executed by the server classes.
 */
public final class BotFightBridge {
    private static final JsonMapper JSON = new JsonMapper();
    private static final UUID CANDIDATE_ID = UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final UUID OPPONENT_ID = UUID.fromString("00000000-0000-0000-0000-000000000002");

    private BotFightBridge() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("expected operation: contracts, validate, or simulate");
        Object response = switch (args[0]) {
            case "contracts" -> contracts();
            case "validate" -> validate(readInput());
            case "validate-batch" -> validateBatch(readInput());
            case "simulate" -> simulate(readInput());
            case "simulate-batch" -> simulateBatch(readInput());
            default -> throw new IllegalArgumentException("unknown operation: " + args[0]);
        };
        System.out.println(JSON.writeValueAsString(response));
    }

    private static JsonNode readInput() throws Exception {
        return JSON.readTree(new String(System.in.readAllBytes(), StandardCharsets.UTF_8));
    }

    private static Map<String, Object> contracts() {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("contractVersion", "bot-fight-ai-game-knowledge-v1");
        root.put("source", Map.of(
                "repository", "botfight",
                "revision", System.getProperty("botfight.source.revision", "unknown"),
                "dirty", Boolean.parseBoolean(System.getProperty("botfight.source.dirty", "false"))));
        root.put("rulesetVersion", DuelSimulationService.DUEL_RULESET_VERSION);
        root.put("brainSchemaVersion", "bot-logic-tree-v1");
        root.put("validatorVersion", "bot-brain-submission-v1");
        root.put("arena", Map.of(
                "width", ArenaUnits.WIDTH,
                "height", ArenaUnits.HEIGHT,
                "spawnEdgeMargin", ArenaUnits.SPAWN_EDGE_MARGIN,
                "fixedStepMs", 100,
                "botSize", 60));
        root.put("gameConfig", new GameConfigCatalog().duelV1());
        root.put("closingZone", ClosingZoneConfig.duelV1());
        root.put("limits", Map.of(
                "maxSimulationBots", DuelSimulationService.MAX_SIMULATION_BOTS,
                "maxRoots", 100,
                "maxActionNodes", 100,
                "maxTotalConditions", 300,
                "maxCustomVariables", 100,
                "maxNumberedBotSelectables", BotLogicContracts.MAX_NUMBERED_BOT_SELECTABLES,
                "customNumberMagnitude", BotLogicContracts.CUSTOM_NUMBER_LIMIT,
                "numberDecimalPlaces", BotLogicContracts.NUMBER_DECIMAL_PLACES));
        root.put("standardAbilities", GameConfigCatalog.STANDARD_ABILITY_ORDER);
        root.put("abilityNames", AbilityRegistry.all());
        root.put("abilityDefinitions", Abilities.CATALOG);
        root.put("abilityContracts", AbilityContracts.all());

        Map<String, Object> logic = new LinkedHashMap<>();
        logic.put("commonActions", List.of(
                BotLogicContracts.ACTION_NONE,
                BotLogicContracts.ACTION_VARIABLE,
                BotLogicContracts.ACTION_MOVE_WALK,
                BotLogicContracts.ACTION_ROTATE_TOWARD_TARGET));
        logic.put("abilityActions", AbilityContracts.actions());
        logic.put("actionContracts", actionContracts());
        logic.put("selectables", BotLogicContracts.selectableContracts());
        logic.put("variables", BotLogicContracts.variableContracts());
        logic.put("variableContracts", variableContracts());
        logic.put("statusEffects", BotLogicContracts.statusEffects());
        logic.put("selectableOrders", BotLogicContracts.selectableOrders());
        logic.put("movementModes", BotLogicContracts.movementModes());
        logic.put("absoluteDirections", BotLogicContracts.absoluteDirections());
        logic.put("numericComparators", BotLogicContracts.numericComparators());
        logic.put("booleanComparators", BotLogicContracts.booleanComparators());
        logic.put("conditionTypes", List.of("always", "expression"));
        logic.put("conditionJoins", List.of("and", "or"));
        logic.put("customVariableOperations", List.of("set", "add", "subtract", "modulo"));
        root.put("botLogic", logic);
        return root;
    }

    private static Map<String, Object> actionContracts() {
        Map<String, Object> contracts = new LinkedHashMap<>();
        List<Object> actions = new ArrayList<>();
        actions.add(BotLogicContracts.ACTION_NONE);
        actions.add(BotLogicContracts.ACTION_VARIABLE);
        actions.add(BotLogicContracts.ACTION_MOVE_WALK);
        actions.add(BotLogicContracts.ACTION_ROTATE_TOWARD_TARGET);
        actions.addAll(AbilityContracts.actions());
        for (Object action : actions) {
            BotLogicContracts.ActionContract contract = BotLogicContracts.actionContract(action);
            if (contract == null) continue;
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("action", action);
            value.put("head", contract.head().name());
            value.put("variableAction", contract.variableAction());
            value.put("movementConfig", contract.movementConfig());
            value.put("coordinateTarget", contract.coordinateTarget());
            value.put("locationTarget", contract.locationTarget());
            value.put("orientationConfig", contract.orientationConfig());
            value.put("angleTarget", contract.angleTarget());
            if (contract.targetMode() != null) value.put("targetMode", contract.targetMode());
            value.put("usesTarget", BotLogicContracts.actionUsesTarget(action));
            value.put("configuration", actionConfiguration(contract));
            contracts.put(String.valueOf(action), value);
        }
        return contracts;
    }

    private static Map<String, Object> actionConfiguration(BotLogicContracts.ActionContract contract) {
        Map<String, Object> configuration = new LinkedHashMap<>();
        switch (contract.head()) {
            case NONE -> {
                configuration.put("requiredFields", List.of("action"));
                configuration.put("optionalFields", List.of());
            }
            case VARIABLE -> {
                configuration.put("requiredFields", List.of("action", "variableId", "operation", "operand"));
                configuration.put("optionalFields", List.of("terms"));
                configuration.put("operations", List.of("set", "add", "subtract", "modulo"));
                configuration.put("operandTypes", List.of("number", "boolean", "variable"));
            }
            case MOVEMENT -> {
                configuration.put("requiredFields", List.of("action", "movementMode"));
                configuration.put("optionalFields", List.of(
                        "selectable", "targetOffsetX", "targetOffsetY", "targetX", "targetY",
                        "movementDirection"));
                configuration.put("movementModes", BotLogicContracts.movementModes());
                configuration.put("absoluteDirections", BotLogicContracts.absoluteDirections());
                configuration.put("targetModes", List.of("target", "coordinates", "absolute"));
            }
            case ROTATION -> {
                configuration.put("requiredFields", List.of("action", "selectable"));
                configuration.put("optionalFields", List.of("targetMode", "targetX", "targetY", "targetAngle", "phaseFacingMode"));
                configuration.put("targetModes", List.of("target", "coordinates", "angle"));
                configuration.put("angleRange", List.of(-360.0, 360.0));
            }
            case ABILITY -> {
                configuration.put("requiredFields", List.of("action"));
                configuration.put("optionalFields", List.of(
                        "selectable", "targetMode", "targetX", "targetY", "targetAngle",
                        "targetOffsetX", "targetOffsetY", "movementMode", "movementDirection",
                        "phaseFacingMode"));
                configuration.put("targetModes", List.of("target", "coordinates", "angle"));
                configuration.put("movementModes", BotLogicContracts.movementModes());
                configuration.put("absoluteDirections", BotLogicContracts.absoluteDirections());
                configuration.put("angleRange", List.of(-360.0, 360.0));
            }
        }
        return configuration;
    }

    private static Map<String, Object> variableContracts() {
        Map<String, Object> contracts = new LinkedHashMap<>();
        for (Map.Entry<String, BotLogicContracts.VariableContract> entry
                : BotLogicContracts.variableContracts().entrySet()) {
            BotLogicContracts.VariableContract contract = entry.getValue();
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("id", contract.id());
            value.put("valueType", contract.valueType().name());
            value.put("supportsSelectable", contract.supportsSelectable());
            value.put("scope", contract.scope().name());
            value.put("source", contract.source().name());
            value.put("tags", contract.tags());
            value.put("pairVariable", contract.isPairVariable());
            value.put("requiresAbility", contract.requiresAbility());
            value.put("requiresStatusEffect", contract.requiresStatusEffect());
            value.put("selectableDependency", contract.selectableDependency() == null
                    ? null : contract.selectableDependency().name());
            value.put("selectableIdentities", contract.selectableIdentities().stream()
                    .map(BotLogicContracts.SelectableIdentity::id).toList());
            value.put("pairSelectableIdentitiesSlot0", contract.pairSelectableIdentities(0).stream()
                    .map(BotLogicContracts.SelectableIdentity::id).toList());
            value.put("pairSelectableIdentitiesSlot1", contract.pairSelectableIdentities(1).stream()
                    .map(BotLogicContracts.SelectableIdentity::id).toList());
            value.put("targetModes", contract.targetModes());
            value.put("selectableType", contract.selectableType() == null
                    ? null : contract.selectableType().id());
            value.put("selectableOrderable", contract.selectableOrderable());
            value.put("angle", contract.angle());
            value.put("circularAngle", contract.circularAngle());
            value.put("boundedRelativeBearing", contract.boundedRelativeBearing());
            value.put("relativeBearingMaximum", contract.relativeBearingMaximum());
            value.put("allowsNegativeInteger", contract.allowsNegativeInteger());
            value.put("nonNegativeTime", contract.nonNegativeTime());
            value.put("durationSeconds", contract.durationSeconds());
            value.put("tenthSecondStep", contract.tenthSecondStep());
            contracts.put(entry.getKey(), value);
        }
        return contracts;
    }

    private static Map<String, Object> validate(JsonNode input) {
        JsonNode brain = input != null && input.has("brain") ? input.get("brain") : input;
        List<String> errors = validationService().validateForSimulation(brain);
        return Map.of(
                "validatorVersion", "bot-brain-submission-v1",
                "valid", errors.isEmpty(),
                "errors", errors);
    }

    private static Map<String, Object> validateBatch(JsonNode input) {
        JsonNode items = required(input, "items");
        if (!items.isArray() || items.isEmpty() || items.size() > 20) {
            throw new IllegalArgumentException("items must contain between 1 and 20 candidates");
        }
        List<Map<String, Object>> results = new ArrayList<>();
        BotSubmissionValidationService validator = validationService();
        for (int index = 0; index < items.size(); index += 1) {
            JsonNode item = items.get(index);
            JsonNode brain = item == null ? null : item.get("brain");
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("index", index);
            result.put("candidateId", text(item, "candidateId", null));
            try {
                List<String> errors = validator.validateForSimulation(brain);
                result.put("valid", errors.isEmpty());
                result.put("errors", errors);
            } catch (StackOverflowError | RuntimeException failure) {
                result.put("valid", false);
                result.put("errors", List.of("validator rejected unsafe input: " + failure.getClass().getSimpleName()));
            }
            results.add(result);
        }
        return Map.of("validatorVersion", "bot-brain-submission-v1", "results", results);
    }

    private static Map<String, Object> simulate(JsonNode input) {
        String scenarioId = text(input, "scenarioId", "scenario-1");
        long seed = input.path("seed").asLong(1L);
        JsonNode candidateBrain = required(input, "candidateBrain");
        JsonNode opponentBrain = required(input, "opponentBrain");
        BotSubmissionValidationService validator = validationService();
        List<String> candidateErrors = validator.validateForSimulation(candidateBrain);
        List<String> opponentErrors = validator.validateForSimulation(opponentBrain);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("scenarioId", scenarioId);
        response.put("rulesetVersion", DuelSimulationService.DUEL_RULESET_VERSION);
        response.put("seed", seed);
        response.put("candidateValidationErrors", candidateErrors);
        response.put("opponentValidationErrors", opponentErrors);
        if (!candidateErrors.isEmpty() || !opponentErrors.isEmpty()) {
            response.put("status", "REJECTED");
            return response;
        }

        DuelSimulationService simulator = simulator();
        DuelSimulationRequest request = new DuelSimulationRequest(
                UUID.nameUUIDFromBytes(scenarioId.getBytes(StandardCharsets.UTF_8)),
                DuelSimulationService.DUEL_RULESET_VERSION,
                seed,
                new DuelArenaRequest(ArenaUnits.WIDTH, ArenaUnits.HEIGHT,
                        ClosingZoneConfig.duelV1().simulationDurationMs()),
                List.of(
                        new DuelBotRequest(CANDIDATE_ID, "candidate", 1,
                                ArenaUnits.WIDTH / 2.0, ArenaUnits.SPAWN_EDGE_MARGIN,
                                180.0, 60, "custom", candidateBrain, null, 1),
                        new DuelBotRequest(OPPONENT_ID, "opponent", 2,
                                ArenaUnits.WIDTH / 2.0, ArenaUnits.HEIGHT - ArenaUnits.SPAWN_EDGE_MARGIN,
                                0.0, 60, "custom", opponentBrain, null, 2)));
        MatchReplayDTO replay = simulator.simulateCompact(request);
        response.put("status", "COMPLETED");
        response.put("result", replay.result());
        response.put("winner", CANDIDATE_ID.equals(replay.winnerUserId())
                ? "candidate" : OPPONENT_ID.equals(replay.winnerUserId()) ? "opponent" : null);
        response.put("message", replay.message());
        response.put("finalBots", finalBots(replay));
        return response;
    }

    private static Map<String, Object> simulateBatch(JsonNode input) {
        JsonNode scenarios = required(input, "scenarios");
        if (!scenarios.isArray()) throw new IllegalArgumentException("scenarios must be an array");
        if (scenarios.isEmpty() || scenarios.size() > 200) {
            throw new IllegalArgumentException("scenarios must contain between 1 and 200 items");
        }
        List<Map<String, Object>> results = new ArrayList<>();
        for (int index = 0; index < scenarios.size(); index += 1) {
            JsonNode scenario = scenarios.get(index);
            try {
                results.add(simulate(scenario));
            } catch (StackOverflowError | RuntimeException exception) {
                Map<String, Object> failure = new LinkedHashMap<>();
                failure.put("scenarioId", text(scenario, "scenarioId", "scenario-" + index));
                failure.put("status", "FAILED");
                failure.put("failureType", exception.getClass().getSimpleName());
                failure.put("message", exception.getMessage());
                results.add(failure);
            }
        }
        return Map.of(
                "rulesetVersion", DuelSimulationService.DUEL_RULESET_VERSION,
                "scenarioCount", results.size(),
                "results", results);
    }

    private static List<Map<String, Object>> finalBots(MatchReplayDTO replay) {
        if (replay.frames() == null || replay.frames().isEmpty()) return List.of();
        MatchReplayDTO.ReplayFrameDTO frame = replay.frames().get(replay.frames().size() - 1);
        List<Map<String, Object>> bots = new ArrayList<>();
        for (MatchReplayDTO.ReplayBotDTO bot : frame.bots()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("slot", bot.slot());
            item.put("teamNumber", bot.teamNumber());
            item.put("hp", bot.hp());
            item.put("x", bot.x());
            item.put("y", bot.y());
            bots.add(item);
        }
        return bots;
    }

    private static BotSubmissionValidationService validationService() {
        return new BotSubmissionValidationService(JSON, new GameConfigCatalog());
    }

    private static DuelSimulationService simulator() {
        BotStateService state = new BotStateService(new GameConfigCatalog(), new BotCodeService());
        ActionExecutionService actions = new ActionExecutionService(state);
        ConditionResolutionService conditions = new ConditionResolutionService(
                new ConditionEvaluationService(), actions);
        return new DuelSimulationService(conditions, new ReplayMappingService(), state, actions);
    }

    private static JsonNode required(JsonNode input, String field) {
        JsonNode value = input == null ? null : input.get(field);
        if (value == null || value.isNull()) throw new IllegalArgumentException(field + " is required");
        return value;
    }

    private static String text(JsonNode input, String field, String fallback) {
        JsonNode value = input == null ? null : input.get(field);
        return value != null && value.isTextual() ? value.asText() : fallback;
    }
}
