#!/bin/bash
# Stage 1B-CF 运行器：崩溃自动重启（WSL2 驱动瞬断），断点续跑
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PYTHONPATH=.
PY=/home/MMCP/miniforge3/envs/safeLoop/bin/python
for attempt in 1 2 3 4 5; do
  echo "[run_cf] attempt $attempt $(date)"
  RESUME=""
  if [ $attempt -gt 1 ]; then RESUME="True"; fi
  $PY -c "
import sys; sys.path.insert(0, '.')
from experiments.stage1cf import main
import json
from utils.io import load_yaml
cfg = load_yaml('configs/hardware/rtx4060_8g_1bb.yaml')
resume = '$RESUME' == 'True'
main('configs/hardware/rtx4060_8g_1bb.yaml', resume=resume)
" && exit 0
  echo "[run_cf] crashed (attempt $attempt), sleeping 120s before retry"
  sleep 120
done
echo "[run_cf] FAILED after 5 attempts"
exit 1
