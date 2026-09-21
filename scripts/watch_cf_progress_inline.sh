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
  # 相位级实时（来自 PHASE 行；旧进程无此行时回退为轮级显示）
  PHASE_LINE=$(grep -aE "PHASE cond=" "$LOG" 2>/dev/null | tail -1)
  PHASE_INFO=""
  if [ -n "$PHASE_LINE" ]; then
    P_COND=$(echo "$PHASE_LINE" | grep -oE "cond=[A-Z_0-9]+" | cut -d= -f2)
    P_NAME=$(echo "$PHASE_LINE" | grep -oE "phase=[a-z]+" | cut -d= -f2)
    P_ITEM=$(echo "$PHASE_LINE" | grep -oE "item=[0-9]+/[0-9]+" | cut -d= -f2-)
    P_TS=$(echo "$PHASE_LINE" | grep -oE "[0-9]{2}:[0-9]{2}:[0-9]{2}" | head -1)
    PHASE_INFO="|$P_COND·${P_NAME} ${P_ITEM} "
    [ -n "$P_TS" ] && PHASE_INFO="$PHASE_INFO($(date -d "$P_TS" '+%H:%M' 2>/dev/null)) "
  fi
  LINE="CF实验 $DONE/$TOTAL [$(draw_bar $((DONE*BAR_W/TOTAL)) $BAR_W)] ${PCT}% $PHASE_INFO"
  LINE="$LINE|r${ROUND_N}/5 ${ROUND_EL}m |~${PACE}m/轮|ETA $(fmt_hm $REM_MIN)→$(date -d "+$REMAIN minutes" '+%H:%M' 2>/dev/null)"
  # 实时模式：每秒走秒表；日志一有新行立即重绘（文件大小监测，无 inotify 依赖）
  printf '\r%-110s' "$LINE"
  # 单行显示：错误流静默，秒级时钟 + 日志增长即时重绘
  PRE_SIZE=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
  I=0
  while [ $I -lt 10 ]; do
    sleep 0.1
    NOW_SIZE=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
    [ "$NOW_SIZE" != "$PRE_SIZE" ] && break
    I=$((I + 1))
  done
done
