#!/bin/bash
# Stage 1B-R 主实验运行器：四分支顺序 + 评估 + shadow + 报告；崩溃自动重启（始终 resume）
export PYTHONPATH=.
PY=/home/MMCP/miniforge3/envs/safeLoop/bin/python
CFG=configs/hardware/rtx4060_8g_1br.yaml
LOG=outputs/logs/stage1b_r.log

run_step() {
  local what=$1
  for attempt in 1 2 3 4 5; do
    echo "[run_1br] $what attempt $attempt $(date)"
    $PY -c "
import sys; sys.path.insert(0, '.')
from experiments.stage1br import main
main('$what', '$CFG', resume=True)
" && return 0
    echo "[run_1br] $what crashed (attempt $attempt), sleeping 120s"
    sleep 120
  done
  echo "[run_1br] $what FAILED after 5 attempts"
  exit 1
}

for STEP in A B C D EVAL SHADOW REPORT; do
  run_step $STEP
done
echo "[run_1br] ALL DONE $(date)"
