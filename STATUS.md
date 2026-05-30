---
name: capcutai
description: 캡컷 에이전트 — 한국어 토킹영상 자동편집기 (mp4/mov→캡컷 드래프트)
status: active
progress: 90
updated: 2026-05-30
tags: [video, capcut, whisper, fastapi]
---

# 마일스톤

- [x] Step 0: 환경 점검 (Mac arm64 → 트랙 A) + pycapcut API 검증
- [x] 1단: silence_detect + build_draft → 점프컷 드래프트 (캡컷 8.2.0 실제 재생 검증 완료)
- [x] 2단: FastAPI + 정적 HTML 1장 (drag/drop + SSE stepper)
- [x] 3단: mlx-whisper Transcript(세그먼트+단어) + 세그먼트 단위 자막 (캡컷 자막 재생 검증 완료)
- [x] 4단: filler_ng + cuts (잔말 자동 컷 + NG 표시) + 결과 카드 transcript (캡컷 재생 검증 완료)
- [x] 5단: 영상 프리뷰 + 보존 구간 사용자 마킹 ([/] 단축키) + 쉼 감도 슬라이더 (브라우저 검증, 사용자 캡컷 최종확인 대기)
- [x] 배포: 애플 실리콘 맥 지인 공유용 설치 키트(install/run .command + README) + GitHub Public (github.com/dawon1982/capcutai)

# 개발 로그

## 2026-05-30

- 배포(설치형 공유). 애플 실리콘 맥 지인용: requirements.txt(의존성 고정), install.command(ffmpeg·venv·모델 자동), run.command(서버+브라우저), README. 임시 venv(Python 3.13)로 requirements 완전성·mlx_whisper import 검증. GitHub Public 푸시: github.com/dawon1982/capcutai. (참고: mlx-whisper는 애플 실리콘 전용이라 Vercel/클라우드 배포 불가 — 로컬 설치형으로 결정.)
- 5단 완료(브라우저 검증). 분석(무음→ASR→잔말)과 드래프트 빌드를 분리: 처리 후 항상 '검토 화면'(원본 영상 플레이어 + 타임라인 + 보존구간 목록). [/] 키로 보존구간 추가, delete로 삭제, 타임라인 클릭 seek, NG 막대 원클릭 제거. '드래프트 만들기'로 사용자 확정 keeps 빌드(/api/build). 영상은 /api/video Range로 서빙. 말끝 잘림 대응: compute_keep_segments에 패딩(0.15s)으로 단어 끝소리·호흡 보존, 최소무음 0.3→0.5s. '쉼 감도' 슬라이더(/api/reanalyze, ASR 재실행 없이 무음만 재검출+잔말 유지). preview MCP로 [/]·delete·NG제거·슬라이더·빌드 전 흐름 + 결과 keeps 일치 검증, 콘솔 무에러.
- 4단 완료. app/script_edit.py: 잔말(음/어 등) 단어 타임스탬프로 자동 컷 — whisper 끝 타임스탬프가 짧게 끊겨 트레일링 소리가 남는 문제를 '다음 단어 시작까지' 잘라 해결. NG(반복 문장)는 인접 세그먼트 유사도로 검출해 표시만(자동 컷 안 함). 자막에서도 잔말 단어 제거. 결과 카드에 대본 전문+NG 목록 노출(브라우저 스크린샷 검증). 캡컷 함정 추가 해결(app/draft.py _stage_media): 캡컷은 샌드박스라 컨테이너 밖 원본을 못 읽어 '파일 액세스 불가' → 미디어를 드래프트 폴더 안으로 하드링크(복사비용0)로 반입. 잔말 컷+자막 캡컷 재생 직접 검증 통과.
- 3단 완료. mlx-whisper(large-v3-turbo)로 한국어 전사(세그먼트+단어, 내용해시 캐시, asyncio.Lock 직렬화 — numba 동시호출 segfault 방지). ASR 세그먼트를 점프컷 타임라인에 매핑(컷 구간은 보존 경계로 스냅)해 자막 트랙(흰 글자+검은 외곽선, 하단) 추가. 한국어 TTS 검증 클립(16.7s→13.75s, 무음2/세그3) → 캡컷에서 자막 재생 직접 검증 통과.
- 2단 완료. FastAPI(app/server.py) + 정적 HTML 1장(app/static/index.html) + 비동기 파이프라인(app/pipeline.py). 드래그앤드롭 업로드 → SSE 스테퍼(무음→ASR→잔말→드래프트). asr/filler는 아직 stub. 디자인: 다크 모노+그린 1색. 포트 8770(8765는 대시보드가 점유). 백엔드 curl + 브라우저 실제 SSE→DOM + 스크린샷으로 검증.
- 1단 완료. ffmpeg silencedetect로 무음 검출 → pycapcut으로 점프컷 드래프트 생성. 합성 클립(8.5s→6.0s) 캡컷 8.2.0에서 직접 재생 검증 통과.
- 캡컷 8.2.0 함정 2건 해결(app/draft.py _finalize_draft): pycapcut가 draft_meta_info.json의 tm_duration을 0으로 둬서 00:00/재생불가 → 실제 길이 패치. 신버전 캡컷은 draft_info.json을 읽어 → draft_content.json 복사본 생성. pycapcut 시간단위는 µs이고 float은 이미 µs로 해석됨(초→µs 직접 변환 필요).
- 초기화: 환경 점검, python3.11 venv, pycapcut 0.0.3 설치.
