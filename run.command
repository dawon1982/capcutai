#!/bin/bash
# 더블클릭 실행 스크립트
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "❌ 먼저 'install.command'를 더블클릭해 설치하세요."
  exit 1
fi

echo "캡컷 에이전트 실행 중... 브라우저가 곧 열립니다."
echo "종료하려면 이 터미널 창을 닫거나 Ctrl+C 를 누르세요."

# 2초 뒤 브라우저 자동 오픈, 서버는 이 창에서 포그라운드 실행
( sleep 2; open "http://localhost:8770" ) &
exec ./.venv/bin/python -m uvicorn app.server:app --port 8770
