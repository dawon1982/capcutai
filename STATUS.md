---
name: capcutai
description: 캡컷 에이전트 — 한국어 토킹영상 자동편집기 (mp4/mov→캡컷 드래프트)
status: active
progress: 20
updated: 2026-05-30
tags: [video, capcut, whisper, fastapi]
---

# 마일스톤

- [x] Step 0: 환경 점검 (Mac arm64 → 트랙 A) + pycapcut API 검증
- [x] 1단: silence_detect + build_draft → 점프컷 드래프트 (캡컷 8.2.0 실제 재생 검증 완료)
- [ ] 2단: FastAPI + 정적 HTML 1장 (drag/drop + SSE stepper)
- [ ] 3단: mlx-whisper Transcript(세그먼트+단어) + 세그먼트 단위 자막
- [ ] 4단: filler_ng + cuts (잔말/NG 통합 컷) + 결과 카드 transcript
- [ ] 5단: 영상 프리뷰 + 보존 구간 사용자 마킹 ([/] 단축키)

# 개발 로그

## 2026-05-30

- 1단 완료. ffmpeg silencedetect로 무음 검출 → pycapcut으로 점프컷 드래프트 생성. 합성 클립(8.5s→6.0s) 캡컷 8.2.0에서 직접 재생 검증 통과.
- 캡컷 8.2.0 함정 2건 해결(app/draft.py _finalize_draft): pycapcut가 draft_meta_info.json의 tm_duration을 0으로 둬서 00:00/재생불가 → 실제 길이 패치. 신버전 캡컷은 draft_info.json을 읽어 → draft_content.json 복사본 생성. pycapcut 시간단위는 µs이고 float은 이미 µs로 해석됨(초→µs 직접 변환 필요).
- 초기화: 환경 점검, python3.11 venv, pycapcut 0.0.3 설치.
