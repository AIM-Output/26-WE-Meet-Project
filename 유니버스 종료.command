#!/bin/bash
# 유니버스 종료 (맥) — 8000 포트에서 듣고 있는 로컬 서버를 끝낸다. Windows "유니버스 종료.cmd" 와 같다.
PIDS="$(lsof -ti tcp:8000 -sTCP:LISTEN 2>/dev/null)"
if [ -z "$PIDS" ]; then
  echo "켜져 있는 서버가 없습니다."
else
  kill $PIDS && echo "서버를 종료했습니다. (PID $(echo $PIDS))"
fi
