#!/usr/bin/env bash
# SafeLoop 1B-R 主实验进度（tqdm 式单行：分支·相位·条目 + ETA）
# 用法: bash scripts/watch_1br_progress.sh   (Ctrl+C 退出不影响实验)
LOG=outputs/logs/stage1b_r.log
TOTAL=1000
BAR_W=30
DEFAULT_ROUND_MIN=25
EVAL_MIN=25   # EVAL+SHADOW+REPORT 收尾
START_TS=$(date +%s)

draw_bar() { local f=$1 w=$2 e=$((w-f)) out=""; [ $f -lt 0 ] && f=0; [ $f -gt $w ] && f=$w
  for ((i=0;i<f;i++)); do out+="█"; done; for ((i=0;i<e;i++)); do out+="░"; done; printf '%s' "$out"; }
fmt_hm() { printf '%dh%02dm' $(($1/60)) $(($1%60)); }

BR_QUERIES=(350 350 150 150)   # A B C D
BR_ORDER=(A B C D)

while true; do
  DONE=0
  for BR in "${BR_ORDER[@]}"; do
    CKPT=outputs/checkpoints/stage1b_r_4060_${BR}.json
    S=0
    [ -f "$CKPT" ] && S=$(python3 -c "
import json; d=json.load(open('$CKPT')); print(sum(len(s['steps']) for s in d['slots']))" 2>/dev/null)
    DONE=$((DONE + S))
  done
  NOW=$(date +%s); ELAPSED=$(( (NOW - START_TS) / 60 ))
  PHASE_LINE=$(grep -aE "PHASE cond=" "$LOG" 2>/dev/null | tail -1)
  STEP_LINE=$(grep -aE "^\[run_1br\] [A-Z]+ (attempt|ALL)" "$LOG" 2>/dev/null | tail -1)
  STEP_NAME=$(echo "$STEP_LINE" | grep -oE "\[run_1br\] [A-Z]+" | grep -oE "[A-Z]+$")
  PH=""
  if [ -n "$PHASE_LINE" ]; then
    P_COND=$(echo "$PHASE_LINE" | grep -oE "cond=[A-Z_0-9]+" | cut -d= -f2)
    P_NAME=$(echo "$PHASE_LINE" | grep -oE "phase=[a-z]+" | cut -d= -f2)
    P_ITEM=$(echo "$PHASE_LINE" | grep -oE "item=[0-9]+/[0-9]+" | cut -d= -f2-)
    PH="|$P_COND·$P_NAME $P_ITEM "
  fi
  # 节奏（round 行中位间隔）+ ETA
  PACE=$DEFAULT_ROUND_MIN
  ROUNDS_DONE=$(grep -acE "INFO round [0-9]+:" "$LOG" 2>/dev/null); [ -z "$ROUNDS_DONE" ] && ROUNDS_DONE=0
  if [ "$ROUNDS_DONE" -ge 2 ]; then
    PACE=$(grep -aE "INFO round [0-9]+:" "$LOG" | grep -aoE "[0-9]{2}:[0-9]{2}:[0-9]{2}" | python3 -c "
import sys, datetime
ts=[datetime.datetime.strptime(l.strip(),'%H:%M:%S').timestamp() for l in sys.stdin]
d=[b-a for a,b in zip(ts,ts[1:]) if 0<b-a<7200]
print(int(sorted(d)[len(d)//2]/60) if d else 0)" 2>/dev/null)
    [ -z "$PACE" ] || [ "$PACE" -lt 5 ] && PACE=$DEFAULT_ROUND_MIN
  fi
  if [ "$DONE" -gt 0 ] && [ "$ELAPSED" -gt 0 ]; then
    RATE=$(python3 -c "print('{:.1f}'.format($DONE/max(1,$ELAPSED)))")
    REMAIN=$(python3 -c "print(int(($TOTAL-$DONE)/max(0.01,$RATE)) + $EVAL_MIN))")
  else
    REMAIN=$(( 40 * 25 + EVAL_MIN )); RATE="…"
  fi
  PCT=$((DONE * 100 / TOTAL))
  LINE="1B-R $DONE/$TOTAL [$(draw_bar $((DONE*BAR_W/TOTAL)) $BAR_W)] ${PCT}% $PH|step=${STEP_NAME:-init} |${ELAPSED}m |~${PACE}m/轮|v${RATE}/m"
  LINE="$LINE|ETA $(fmt_hm $REMAIN)→$(date -d "+$REMAIN minutes" '+%m-%d %H:%M' 2>/dev/null)"
  printf '\r%-125s' "$LINE"
  PRE=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
  I=0
  while [ $I -lt 10 ]; do
    sleep 0.1
    CUR=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
    [ "$CUR" != "$PRE" ] && break
    I=$((I+1))
  done
done
