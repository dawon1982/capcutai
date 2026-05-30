#!/bin/bash
# 더블클릭 설치 스크립트 (애플 실리콘 맥)
set -e
cd "$(dirname "$0")"

echo "════════════════════════════════════"
echo "  캡컷 에이전트 설치"
echo "════════════════════════════════════"

# 0) 애플 실리콘 확인
if [ "$(uname -m)" != "arm64" ]; then
  echo "⚠️  이 도구의 음성 인식(mlx-whisper)은 애플 실리콘(M칩) 맥 전용입니다."
  echo "    인텔 맥에서는 동작하지 않습니다."
  exit 1
fi

# 1) Python 3 확인
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Python 3가 없습니다."
  echo "   https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요."
  exit 1
fi
echo "✓ Python: $(python3 --version)"

# 2) ffmpeg 확인 (없으면 Homebrew로 설치)
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "ffmpeg가 없어 Homebrew로 설치합니다..."
    brew install ffmpeg
  else
    echo "❌ ffmpeg와 Homebrew가 모두 없습니다."
    echo "   1) https://brew.sh 에서 Homebrew 설치"
    echo "   2) 터미널에서: brew install ffmpeg"
    echo "   3) 이 스크립트를 다시 실행"
    exit 1
  fi
fi
echo "✓ ffmpeg 확인됨"

# 3) 가상환경 + 패키지
echo "가상환경 만들고 패키지 설치 중..."
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -r requirements.txt

# 4) 음성 인식 모델 미리 받기 (약 1.5GB, 처음 한 번만)
echo "음성 인식 모델(약 1.5GB) 다운로드 중... 네트워크에 따라 몇 분 걸립니다."
./.venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/whisper-large-v3-turbo')"

echo ""
echo "✅ 설치 완료!  'run.command'를 더블클릭하면 실행됩니다."
echo "   (캡컷이 설치되어 있어야 결과 드래프트를 열 수 있습니다.)"
