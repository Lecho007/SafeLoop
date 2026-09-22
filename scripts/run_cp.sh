#!/bin/bash
# Stage 1B-CP 运行器：崩溃自动重启，始终 resume
export PYTHONPATH=.
PY=/home/MMCP/miniforge3/envs/safeLoop/bin/python
for attempt in 1 2 3 4 5; do
  echo "[run_cp] attempt $attempt $(date)"
  $PY -c "
import sys; sys.path.insert(0, '.')
from experiments.stage1cp import main
main('configs/hardware/rtx4060_8g_1bb.yaml', resume=True)
" && exit 0
  echo "[run_cp] crashed (attempt $attempt), sleeping 120s"
  sleep 120
done
echo "[run_cp] FAILED after 5 attempts"; exit 1
