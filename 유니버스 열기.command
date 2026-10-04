#!/bin/bash
# 유니버스 열기 (맥) — 로컬 서버를 백그라운드로 켜고 브라우저로 대시보드를 연다. Windows "유니버스 열기.cmd" 와 같다.
# 서버는 이 창을 닫아도 계속 돈다. 끄기: "유니버스 종료.command". 서버 출력: univ_us_local/backend/server.log
cd "$(dirname "$0")" || exit 1
URL="http://localhost:8000"
LOG="univ_us_local/backend/server.log"

if curl -s -o /dev/null --max-time 2 "$URL/api/status"; then
  open "$URL"
  exit 0
fi

echo "로컬 서버를 시작합니다... (처음이면 패키지 설치로 1~2분 걸릴 수 있습니다)"
nohup ./univ_us_local/backend/run.command > "$LOG" 2>&1 &
SERVER=$!

# 처음엔 패키지 설치 때문에 오래 걸릴 수 있어 최대 180초 기다린다
for _ in $(seq 1 180); do
  if curl -s -o /dev/null --max-time 2 "$URL/api/status"; then
    open "$URL"
    echo "대시보드를 열었습니다 ($URL). 이 창은 닫아도 됩니다."
    exit 0
  fi
  if ! kill -0 "$SERVER" 2>/dev/null; then
    echo ""
    echo "서버가 시작하지 못했습니다. 아래 메시지를 확인하세요 ($LOG):"
    tail -n 20 "$LOG"
    exit 1
  fi
  sleep 1
done
echo ""
echo "서버가 180초 안에 응답하지 않았습니다. $LOG 를 확인하세요."
exit 1
