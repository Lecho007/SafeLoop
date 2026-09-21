#!/usr/bin/env bash
# SafeLoop CF 实验进度 + 剩余时间（实时，含轮内进度与基于实测节奏的 ETA）
# 用法: bash scripts/watch_cf_progress.sh   (Ctrl+C 退出不影响实验)
LOG=outputs/logs/stage1b_cf.log
TOTAL_STEPS=300
DEFAULT_ROUND_MIN=27      # 未见实测前的默认单轮时长（分钟）
EVAL_MIN=10               # 末尾离线评估开销（分钟）

get_ts() { date -d "$1" +%s 2>/dev/null; }

while true; do
  clear
  echo "================ SafeLoop Stage 1B-CF 实验进度 ================"
  RUNNING=0
  if pgrep -f run_cf.sh > /dev/null 2>&1; then RUNNING=1; fi
  ATTEMPT=$(grep -cE "^\[run_cf\] attempt" "$LOG" 2>/dev/null)
  [ -z "$ATTEMPT" ] && ATTEMPT=0
  if [ "$RUNNING" -eq 1 ]; then
    echo "状态: 运行中 (attempt #$ATTEMPT)    PID: $(pgrep -f run_cf.sh | head -1)"
  elif [ -f outputs/reports/stage1b_cf_4060.json ]; then
    echo "状态: ✅ 已完成（报告: outputs/reports/stage1b_cf_4060.json）"
  else
    echo "状态: ⚠ 停止（未完成）"
  fi
  echo "----------------------------------------------------------------"

  # ---- 步数（检查点 + 日志步行）----
  DONE=0
  for COND in CF_10 CF_11; do
    CKPT=outputs/checkpoints/stage1b_cf_4060_${COND}.json
    STEPS=0
    [ -f "$CKPT" ] && STEPS=$(python3 -c "
import json; d=json.load(open('$CKPT')); print(sum(len(s['steps']) for s in d['slots']))" 2>/dev/null || echo 0)
    LOGSTEPS=$(grep -cE "INFO \[$COND\].*round=[0-9]" "$LOG" 2>/dev/null)
    [ -z "$LOGSTEPS" ] && LOGSTEPS=0
    [ "$LOGSTEPS" -gt "$STEPS" ] && STEPS=$LOGSTEPS
    DONE=$((DONE + STEPS))
    FILLED=$((STEPS * 20 / 150)); EMPTY=$((20 - FILLED))
    BAR=$(printf '█%.0s' $(seq 1 $FILLED 2>/dev/null); printf '░%.0s' $(seq 1 $EMPTY 2>/dev/null))
    echo "  $COND  [$BAR] $STEPS/150  ($((STEPS * 100 / 150))%)"
  done
  TOTAL_FILLED=$((DONE * 30 / TOTAL_STEPS)); TOTAL_EMPTY=$((30 - TOTAL_FILLED))
  TOTAL_BAR=$(printf '█%.0s' $(seq 1 $TOTAL_FILLED 2>/dev/null); printf '░%.0s' $(seq 1 $TOTAL_EMPTY 2>/dev/null))
  echo "----------------------------------------------------------------"
  echo "  总进度  [$TOTAL_BAR] $DONE/$TOTAL_STEPS  ($((DONE * 100 / TOTAL_STEPS))%)"

  # ---- 当前轮 + 实测节奏 + ETA（始终显示）----
  if [ "$RUNNING" -eq 1 ]; then
    NOW=$(date +%s)
    LAST_ROUND_LINE=$(grep -E "INFO round [0-9]+:" "$LOG" 2>/dev/null | tail -1)
    ROUND_N=$(echo "$LAST_ROUND_LINE" | grep -oE "round [0-9]+" | grep -oE "[0-9]+")
    ROUND_TS=$(echo "$LAST_ROUND_LINE" | grep -oE "[0-9]{2}:[0-9]{2}:[0-9]{2}" | head -1)
    if [ -n "$ROUND_TS" ] && [ -n "$ROUND_N" ]; then
      R_START=$(get_ts "$(date '+%Y-%m-%d') $ROUND_TS")
      [ -z "$R_START" ] && R_START=$NOW
      ROUND_ELAPSED=$(( (NOW - R_START) / 60 ))
      echo "  当前: round $ROUND_N/5 已进行 ${ROUND_ELAPSED} 分钟"
      # 实测单轮时长：相邻 round 行时间差的中位
      PACE=$(grep -E "INFO round [0-9]+:" "$LOG" | grep -oE "[0-9]{2}:[0-9]{2}:[0-9]{2}" | \
        python3 -c "
import sys, datetime
ts = [datetime.datetime.strptime(l.strip(), '%H:%M:%S').timestamp() for l in sys.stdin]
d = [b-a for a,b in zip(ts, ts[1:]) if 0 < b-a < 7200]
print(int(sorted(d)[len(d)//2]/60) if d else 0)" 2>/dev/null || echo 0)
      [ "$PACE" -lt 5 ] && PACE=$DEFAULT_ROUND_MIN
      # 剩余：当前轮剩余 + 后续轮 + 另一条件全量 + 评估
      ROUNDS_DONE_TOTAL=$(grep -cE "INFO round [0-9]+:" "$LOG")
      REMAIN_ROUNDS=$((10 - ROUNDS_DONE_TOTAL))
      [ "$REMAIN_ROUNDS" -lt 0 ] && REMAIN_ROUNDS=0
      CUR_REMAIN=$(( PACE - ROUND_ELAPSED )); [ "$CUR_REMAIN" -lt 0 ] && CUR_REMAIN=0
      REMAIN_MIN=$(( CUR_REMAIN + (REMAIN_ROUNDS > 0 ? (REMAIN_ROUNDS - 1) * PACE : 0) + EVAL_MIN ))
      echo "  节奏: 单轮 ~${PACE} 分钟（实测） | 剩余轮次: $REMAIN_ROUNDS"
      echo "  ⏱ 剩余时间 ≈ $((REMAIN_MIN / 60)) 小时 $((REMAIN_MIN % 60)) 分钟"
      echo "  🕐 预计完成: $(date -d "+$REMAIN_MIN minutes" '+%H:%M' 2>/dev/null)"
    else
      echo "  当前: 启动中（首个 round 行尚未出现）"
      echo "  ⏱ 剩余时间 ≈ 5 小时（默认估算，首步后精确化）"
    fi
  fi
  echo "----------------------------------------------------------------"
  nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader 2>/dev/null | \
    awk -F', ' '{printf "  GPU: 显存 %s / 利用率 %s / 温度 %s°C\n", $1, $2, $3}'
  echo "================================================================"
  echo "  (每 30 秒刷新 | Ctrl+C 退出不影响实验)"
  sleep 30
done
