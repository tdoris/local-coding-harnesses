  qwen)
    # Qwen Code ships a lot of machinery that costs prompt tokens or extra model calls
    # (workflows, cron, artifacts, computer-use, LLM tool-use summaries, auto-memory,
    # follow-up suggestions, an LLM approval classifier). Give it a self-contained
    # config dir (QWEN_HOME) whose provider entry carries the real context window —
    # otherwise it assumes 200k and never compacts before Ollama truncates.
    qh="$LOG_DIR/qwen-home"; mkdir -p "$qh"
    MODEL="$MODEL" CTX="$CTX" MAX_OUTPUT="$MAX_OUTPUT" BASE_URL="$BASE_URL" python3 - "$qh/settings.json" <<'PYEOF'
import json, os, sys
m, ctx, out, base = os.environ["MODEL"], int(os.environ["CTX"]), int(os.environ["MAX_OUTPUT"]), os.environ["BASE_URL"] + "/v1"
json.dump({
  "$version": 4,
  "env": {"OLLAMA_API_KEY": "ollama"},
  "model": {"name": m},
  "modelProviders": {"openai": [{"id": m, "name": f"{m} (Ollama via local-agent)", "baseUrl": base, "envKey": "OLLAMA_API_KEY",
                                 "generationConfig": {"contextWindowSize": ctx, "samplingParams": {"max_tokens": out}}}]},
  "security": {"auth": {"selectedType": "openai", "baseUrl": base}},
  "context": {"autoCompactThreshold": 0.8},
  "memory": {"enableManagedAutoMemory": False, "enableAutoSkill": False},
  "ui": {"enableFollowupSuggestions": False},
  "tools": {"toolSearch": {"threshold": 3}, "computerUse": {"enabled": False}},
  "experimental": {"cron": False, "artifact": False, "emitToolUseSummaries": False, "agentTeam": False},
}, open(sys.argv[1], "w"), indent=2)
PYEOF
    export QWEN_HOME="$qh"
    export OPENAI_API_KEY=ollama OPENAI_BASE_URL="$BASE_URL/v1" OPENAI_MODEL="$MODEL"
    export QWEN_CODE_DISABLE_WORKFLOWS=1 QWEN_CODE_DISABLE_CRON=1 QWEN_CODE_DISABLE_ARTIFACT=1
    export QWEN_CODE_EMIT_TOOL_USE_SUMMARIES=0 QWEN_DISABLE_AUTO_TITLE=1 QWEN_CODE_SUPPRESS_YOLO_WARNING=1
    qwen --model "$MODEL" --auth-type openai "$@"
    ;;

