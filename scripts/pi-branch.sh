  pi)
    # pi (pi.dev): minimal harness — read/bash/edit/write. Give it a private agent dir so we
    # don't rewrite ~/.pi/agent/models.json; the model entry carries the real context window.
    pd="$LOG_DIR/pi-agent"; mkdir -p "$pd"
    MODEL="$MODEL" CTX="$CTX" MAX_OUTPUT="$MAX_OUTPUT" BASE_URL="$BASE_URL" python3 - "$pd" <<'PYEOF'
import json, os, sys
m, ctx, out, base, d = os.environ["MODEL"], int(os.environ["CTX"]), int(os.environ["MAX_OUTPUT"]), os.environ["BASE_URL"], sys.argv[1]
json.dump({"providers": {"ollama": {
    "api": "openai-completions", "apiKey": "ollama", "baseUrl": base + "/v1",
    "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
    "models": [{"id": m, "name": m, "reasoning": True, "input": ["text", "image"],
                "contextWindow": ctx, "maxTokens": out}]}}}, open(d + "/models.json", "w"), indent=2)
json.dump({"defaultProvider": "ollama", "defaultModel": m}, open(d + "/settings.json", "w"), indent=2)
PYEOF
    export PI_CODING_AGENT_DIR="$pd"
    pi --provider ollama --model "$MODEL" "$@"
    ;;

