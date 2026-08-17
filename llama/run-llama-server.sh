#!/usr/bin/env bash
# llama-server for qwen3.8 with froggeric's fixed chat template (reasoning-effort control)
MODEL=/usr/share/ollama/.ollama/models/blobs/sha256-f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d
TMPL=$(dirname "$(readlink -f "$0")")/chat_template.jinja
PORT=${PORT:-11436}; CTX=${CTX:-81920}
export LD_LIBRARY_PATH=/usr/local/lib/ollama/cuda_v13:/usr/local/lib/ollama:${LD_LIBRARY_PATH:-}
export GGML_BACKEND_PATH=/usr/local/lib/ollama/cuda_v13/libggml-cuda.so
exec /usr/local/lib/ollama/llama-server -m "$MODEL" --alias qwen3.8 --host 127.0.0.1 --port "$PORT" \
  -c "$CTX" -ngl 999 -fa on -ctk q8_0 -ctv q8_0 -np 1 -b 512 -ub 512 \
  --jinja --chat-template-file "$TMPL" --reasoning-format deepseek --reasoning-preserve --reasoning-budget ${REASONING_BUDGET:--1} --chat-template-kwargs "{\"reasoning_effort\":\"${REASONING_EFFORT:-medium}\"}" \
  --spec-type draft-mtp --spec-draft-n-max 4 --spec-draft-backend-sampling \
  --no-webui "$@"
