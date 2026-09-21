#!/usr/bin/env bash
# SafeLoop CF 训练式进度条（原地刷新单行，类似 tqdm；不清屏）
# 用法: bash scripts/watch_cf_progress_inline.sh   (Ctrl+C 退出不影响实验)
LOG=outputs/logs/stage1b_cf.log
TOTAL=300
DEFAULT_ROUND_MIN=27
EVAL_MIN=10
START_TS=$(date +%s)

BAR_W=30
draw_bar() { # $1=filled $2=width
  local f=$1 w=$2 e=$((w - f)) out=""
  [ $f -lt 0 ] && f=0; [ $f -gt $w ] && f=$w
  for ((i=0; i<f; i++)); do out+="█"; done
  for ((i=0; i<e; i++)); do out+="░"; done
  printf '%s' "$out"
}
fmt_hm() { local m=$1; printf '%dh%02dm' $((m/60)) $((m%60)); }

while true; do
  DONE=0
  for COND in CF_10 CF_11; do
    CKPT=outputs/checkpoints/stage1b_cf_4060_${COND}.json
    S=0
    [ -f "$CKPT" ] && S=$(python3 -c "
import json; d=json.load(open('$CKPT')); print(sum(len(s['steps']) for s in d['slots']))" 2>/dev/null)
    LS=$(grep -cE "INFO \[$COND\].*round=[0-9]" "$LOG" 2>/dev/null)
    [ -z "$LS" ] && LS=0
    [ "$LS" -gt "$S" ] && S=$LS
    DONE=$((DONE + S))
  done
  NOW=$(date +%s)
  ELAPSED=$(( (NOW - START_TS) / 60 ))
  # 当前轮 + 实测节奏
  LAST_ROUND_LINE=$(grep -E "INFO round [0-9]+:" "$LOG" 2>/dev/null | tail -1)
  ROUND_N=$(echo "$LAST_ROUND_LINE" | grep -oE "round [0-9]+" | grep -oE "[0-9]+" | head -1)
  ROUND_TS=$(echo "$LAST_ROUND_LINE" | grep -oE "[0-9]{2}:[0-9]{2}:[0-9]{2}" | head -1)
  PACE=$DEFAULT_ROUND_MIN
  ROUNDS_DONE=$(grep -cE "INFO round [0-9]+:" "$LOG" 2>/dev/null); [ -z "$ROUNDS_DONE" ] && ROUNDS_DONE=0
  if [ -n "$ROUND_TS" ]; then
    R_START=$(date -d "$(date '+%Y-%m-%d') $ROUND_TS" +%s 2>/dev/null || echo $NOW)
    ROUND_EL=$(( (NOW - R_START) / 60 ))
    PACE=$(grep -E "INFO round [0-9]+:" "$LOG" | grep -oE "[0-9]{2}:[0-9]{2}:[0-9]{2}" | \
      python3 -c "
import sys, datetime
ts=[datetime.datetime.strptime(l.strip(),'%H:%M:%S').timestamp() for l in sys.stdin]
d=[b-a for a,b in zip(ts,ts[1:]) if 0<b-a<7200]
print(int(sorted(d)[len(d)//2]/60) if d else 0)" 2>/dev/null)
    [ -z "$PACE" ] || [ "$PACE" -lt 5 ] && PACE=$DEFAULT_ROUND_MIN
  else
    ROUND_N=0; ROUND_EL=0
  fi
  REM_ROUNDS=$((10 - ROUNDS_DONE)); [ "$REM_ROUNDS" -lt 0 ] && REM_ROUNDS=0
  CUR_REM=$((PACE - ROUND_EL)); [ "$CUR_REM" -lt 0 ] && CUR_REM=0
  REM_MIN=$(( CUR_REM + (REM_ROUNDS>0 ? (REM_ROUNDS-1)*PACE : 0) + EVAL_MIN ))
  PCT=$((DONE * 100 / TOTAL))
  LINE1="CF实验: $DONE/$TOTAL [$(draw_bar $((DONE*BAR_W/TOTAL)) $BAR_W)] ${PCT}%"
  LINE2="round ${ROUND_N}/5 | 已观测 ${ELAPSED}m | 节奏 ~${PACE}m/轮 | ETA $(fmt_hm $REM_MIN) → $(date -d "+$REM_MIN minutes" '+%H:%M' 2>/dev/null)"
  # 原地刷新（\r 覆盖；预留空格清除残留）
  printf '\r%-%ds' $((BAR_W + 30)) "$LINE1"
  printf '\n\r%s%b' "$LINE2" "$(printf '%*s' $((BAR_W + 40)) '')"
  printf '\r\r\033[A'   # 光标回到第一行
  sleep 5
done
