#!/usr/bin/env bash
# cloud-run.sh <harness>  — full pipeline for one harness against gpt-oss:120b-cloud
t=$1; ROOT=~/repos/scratch/harness-test/cloud; T=$ROOT/tasks; W=$ROOT/$t
mkdir -p $W/tomlq $W/jpatch; cd $W/tomlq && git init -q 2>/dev/null; git -C $W/tomlq config user.email j@x; git -C $W/tomlq config user.name j
cd $W/jpatch && git init -q 2>/dev/null; git -C $W/jpatch config user.email j@x; git -C $W/jpatch config user.name j
LA="local-agent --model gpt-oss:120b-cloud"
runp() { # runp <label> <dir> <cmd...>
  local label=$1 dir=$2; shift 2; local t0=$(date +%s)
  ( cd "$dir" && env -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u GEMINI_API_KEY CLAUDE_OLLAMA_NO_UNLOAD=1 timeout 1500 "$@" </dev/null ) > $W/out-$label.log 2>&1
  echo "### $t $label exit=$? wall=$(( $(date +%s) - t0 ))s"
}
launch() { # launch <phase> <dir> <promptfile> [continue]
  local phase=$1 dir=$2 msg; msg=$(cat "$3"); local cont=${4:-}
  case $t in
    opencode) if [[ -n $cont ]]; then set -- $LA opencode run -c "$msg"; else set -- $LA opencode run "$msg"; fi ;;
    qwen)     if [[ -n $cont ]]; then set -- $LA qwen --approval-mode yolo -c -p "$msg"; else set -- $LA qwen --approval-mode yolo -p "$msg"; fi ;;
    pi)       if [[ -n $cont ]]; then set -- $LA pi -c -p "$msg"; else set -- $LA pi -p "$msg"; fi ;;
    claude)   if [[ -n $cont ]]; then set -- $LA claude --dangerously-skip-permissions -c -p "$msg" --output-format text; else set -- $LA claude --dangerously-skip-permissions -p "$msg" --output-format text; fi ;;
    aider)    case $phase in
                tomlA) set -- $LA aider --yes-always --no-auto-commits --message "$msg" ;;
                tomlB) set -- $LA aider --yes-always --no-auto-commits --restore-chat-history --file tomlq.py --read test_tomlq.py --test-cmd "python3 test_tomlq.py" --auto-test --message "$msg" ;;
                jpatch) set -- $LA aider --yes-always --no-auto-commits --file jpatch.py --read test_jpatch.py --test-cmd "python3 test_jpatch.py" --auto-test --message "$msg" ;;
              esac ;;
  esac
  runp "$phase" "$dir" "$@"
}
# --- Task 1 phase A: spec only
printf '%s\n\nWrite tomlq.py in the current directory. Test it yourself on a few TOML examples (scratch files are fine) before finishing. Reply with one line when done.\n' "$(cat $T/tomlq/spec.md)" > $W/prompt-tomlA.txt
launch tomlA $W/tomlq $W/prompt-tomlA.txt
cp $W/tomlq/tomlq.py $W/tomlq/tomlq.A.py 2>/dev/null
echo "GRADE tomlA hidden: $(python3 $T/tomlq/grade.py $W/tomlq --json)"
# --- Task 1 phase B: tests handed over, session continued
cp $T/tomlq/test_tomlq.py $W/tomlq/
printf 'A test file test_tomlq.py has been added to the current directory. Run `python3 test_tomlq.py`. Fix tomlq.py until every test passes. Rules: do not modify test_tomlq.py; do not use any TOML library (tomllib/toml/tomli/tomlkit); standard library only. When done, reply with the final unittest summary line.\n' > $W/prompt-tomlB.txt
launch tomlB $W/tomlq $W/prompt-tomlB.txt continue
cp $W/tomlq/tomlq.py $W/tomlq/tomlq.B.py 2>/dev/null
echo "GRADE tomlB visible: $(python3 $T/tomlq/grade.py $W/tomlq --visible-only --json)"
echo "GRADE tomlB hidden: $(python3 $T/tomlq/grade.py $W/tomlq --json)"
# --- Task 2: test-first
cp $T/jpatch/test_jpatch.py $W/jpatch/
printf '%s\n' "$(cat $T/jpatch/spec.md)" > $W/prompt-jpatch.txt
launch jpatch $W/jpatch $W/prompt-jpatch.txt
echo "GRADE jpatch visible: $(python3 $T/jpatch/grade.py $W/jpatch --visible-only --json)"
echo "GRADE jpatch hidden: $(python3 $T/jpatch/grade.py $W/jpatch --json)"
echo "PIPELINE-DONE $t"
