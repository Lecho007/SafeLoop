#!/usr/bin/env bash
# SafeLoop CF 实验进度条 + 剩余时间实时显示
# 用法: bash scripts/watch_cf_progress.sh   (Ctrl+C 退出，不影响实验)
LOG=outputs/logs/stage1b_cf.log
CKPT_DIR=outputs/checkpoints
TOTAL_STEPS=300            # 2 条件 × 30 tasks × 5 rounds
ROUND_STEPS=30

while true; do
  clear
  echo "================ SafeLoop Stage 1B-CF 实验进度 ================"
  # 运行状态
  if pgrep -f run_cf.sh > /dev/null 2>&1; then
    STARTED=$(grep -oE "attempt [0-9]+ [A-Za-z]{3} [A-Za-z]{3} [0-9]+ [0-9:]+ CST [0-9]+" "$LOG" 2>/dev/null | tail -1)
    ATTEMPT=$(grep -cE "^\[run_cf\] attempt" "$LOG" 2>/dev/null)
    echo "状态: 运行中 (attempt #$ATTEMPT)    PID: $(pgrep -f run_cf.sh | head -1)"
  else
    if [ -f outputs/reports/stage1b_cf_4060.json ]; then
      echo "状态: ✅ 已完成（报告: outputs/reports/stage1b_cf_4060.json）"
    else
      echo "状态: ⚠ 未运行（未完成）— 用 nohup bash scripts/run_cf.sh 重启"
    fi
  fi
  echo "----------------------------------------------------------------"
  # 各条件步数
  DONE=0
  for COND in CF_10 CF_11; do
    CKPT=$CKPT_DIR/stage1b_cf_4060_${COND}.json
    if [ -f "$CKPT" ]; then
      STEPS=$(python3 -c "
import json
d = json.load(open('$CKPT'))
print(sum(len(s['steps']) for s in d['slots']))" 2>/dev/null || echo 0)
    else
      STEPS=0
    fi
    DONE=$((DONE + STEPS))
    # 进度条
    FILLED=$((STEPS * 20 / 150))
    EMPTY=$((20 - FILLED))
    BAR=$(printf '█%.0s' $(seq 1 $FILLED 2>/dev/null); printf '░%.0s' $(seq 1 $EMPTY 2>/dev/null))
    PCT=$((STEPS * 100 / 150))
    echo "  $COND  [$BAR] $STEPS/150  ($PCT%)"
  done
  # 总进度 + 剩余时间估算
  TOTAL_FILLED=$((DONE * 30 / TOTAL_STEPS))
  TOTAL_EMPTY=$((30 - TOTAL_FILLED))
  TOTAL_BAR=$(printf '█%.0s' $(seq 1 $TOTAL_FILLED 2>/dev/null); printf '░%.0s' $(seq 1 $TOTAL_EMPTY 2>/dev/null))
  PCT=$((DONE * 100 / TOTAL_STEPS))
  echo "----------------------------------------------------------------"
  echo "  总进度  [$TOTAL_BAR] $DONE/$TOTAL_STEPS  ($PCT%)"
  # 速度估算：最近一次 attempt 启动到现在
  if pgrep -f run_cf.sh > /dev/null 2>&1 && [ "$DONE" -gt 0 ]; then
    ATTEMPT_LINE=$(grep -E "^\[run_cf\] attempt" "$LOG" | tail -1)
    START_TS=$(date -d "$(echo "$ATTEMPT_LINE" | grep -oE '[A-Za-z]{3} [A-Za-z]{3} +[0-9]+ [0-9:]+' | head -1)" +%s 2>/dev/null || date +%s)
    NOW=$(date +%s)
    ELAPSED=$((NOW - START_TS))
    # attempt 内已跑步数（检查点总量 - attempt 开始时的量不可得，用总量近似）
    RATE=$(python3 -c "print('{:.1f}'.format($DONE / max(1, $ELAPSED / 60)))" 2>/dev/null)
    if [ -n "$RATE" ] && [ "$RATE" != "0.0" ]; then
      REMAIN=$(python3 -c "print('{:.0f}'.format(($TOTAL_STEPS - $DONE) / $RATE))" 2>/dev/null)
      HOURS=$((REMAIN / 60)); MINS=$((REMAIN % 60))
      echo "  已运行 $((ELAPSED / 60)) 分钟 | 速度 ~${RATE} 步/分钟 | 剩余 ≈ ${HOURS}小时${MINS}分钟"
      echo "  预计完成: $(date -d "+$REMAIN minutes" '+%H:%M' 2>/dev/null)"
    fi
  fi
  # GPU 状态
  echo "----------------------------------------------------------------"
  nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader 2>/dev/null | \
    awk -F', ' '{printf "  GPU: 显存 %s / 利用率 %s / 温度 %s°C\n", $1, $2, $3}'
  echo "================================================================"
  echo "  (每 30 秒刷新 | Ctrl+C 退出不影响实验)"
  sleep 30
done
