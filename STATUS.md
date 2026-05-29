---
name: capcutai
description: 캡컷 에이전트 — 한국어 토킹영상 자동편집기 (mp4/mov→캡컷 드래프트)
status: active
progress: 55
updated: 2026-05-30
tags: [video, capcut, whisper, fastapi]
---

# 마일스톤

- [x] Step 0: 환경 점검 (Mac arm64 → 트랙 A) + pycapcut API 검증
- [x] 1단: silence_detect + build_draft → 점프컷 드래프트 (캡컷 8.2.0 실제 재생 검증 완료)
- [x] 2단: FastAPI + 정적 HTML 1장 (drag/drop + SSE stepper)
- [x] 3단: mlx-whisper Transcript(세그먼트+단어) + 세그먼트 단위 자막 (캡컷 자막 재생 검증 완료)
- [ ] 4단: filler_ng + cuts (잔말/NG 통합 컷) + 결과 카드 transcript
- [ ] 5단: 영상 프리뷰 + 보존 구간 사용자 마킹 ([/] 단축키)

# 개발 로그

## 2026-05-30

- 3단 완료. mlx-whisper(large-v3-turbo)로 한국어 전사(세그먼트+단어, 내용해시 캐시, asyncio.Lock 직렬화 — numba 동시호출 segfault 방지). ASR 세그먼트를 점프컷 타임라인에 매핑(컷 구간은 보존 경계로 스냅)해 자막 트랙(흰 글자+검은 외곽선, 하단) 추가. 한국어 TTS 검증 클립(16.7s→13.75s, 무음2/세그3) → 캡컷에서 자막 재생 직접 검증 통과.
- 2단 완료. FastAPI(app/server.py) + 정적 HTML 1장(app/static/index.html) + 비동기 파이프라인(app/pipeline.py). 드래그앤드롭 업로드 → SSE 스테퍼(무음→ASR→잔말→드래프트). asr/filler는 아직 stub. 디자인: 다크 모노+그린 1색. 포트 8770(8765는 대시보드가 점유). 백엔드 curl + 브라우저 실제 SSE→DOM + 스크린샷으로 검증.
- 1단 완료. ffmpeg silencedetect로 무음 검출 → pycapcut으로 점프컷 드래프트 생성. 합성 클립(8.5s→6.0s) 캡컷 8.2.0에서 직접 재생 검증 통과.
- 캡컷 8.2.0 함정 2건 해결(app/draft.py _finalize_draft): pycapcut가 draft_meta_info.json의 tm_duration을 0으로 둬서 00:00/재생불가 → 실제 길이 패치. 신버전 캡컷은 draft_info.json을 읽어 → draft_content.json 복사본 생성. pycapcut 시간단위는 µs이고 float은 이미 µs로 해석됨(초→µs 직접 변환 필요).
- 초기화: 환경 점검, python3.11 venv, pycapcut 0.0.3 설치.
