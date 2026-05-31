---
name: capcutai
description: 캡컷 에이전트 — 한국어 토킹영상 자동편집기 (mp4/mov→캡컷 드래프트)
status: done
progress: 100
updated: 2026-05-30
tags: [video, capcut, whisper, fastapi]
---

# 마일스톤

- [x] Step 0: 환경 점검 (Mac arm64 → 트랙 A) + pycapcut API 검증
- [x] 1단: silence_detect + build_draft → 점프컷 드래프트 (캡컷 8.2.0 실제 재생 검증 완료)
- [x] 2단: FastAPI + 정적 HTML 1장 (drag/drop + SSE stepper)
- [x] 3단: mlx-whisper Transcript(세그먼트+단어) + 세그먼트 단위 자막 (캡컷 자막 재생 검증 완료)
- [x] 4단: filler_ng + cuts (잔말 자동 컷 + NG 표시) + 결과 카드 transcript (캡컷 재생 검증 완료)
- [x] 5단: 영상 프리뷰 + 보존 구간 사용자 마킹 ([/] 단축키) + 쉼/말끝 감도 슬라이더 (사용자 캡컷 확인 완료)
- [x] 배포: 애플 실리콘 맥 지인 공유용 설치 키트(install/run .command + README) + GitHub Public (github.com/dawon1982/capcutai)

# 개발 로그

## 2026-06-01

- 즉시 반복(말더듬·리테이크) 자동 컷. script_edit.find_repeat_cuts: 단어 스트림에서 2단어 이상 구절이 바로 이어 정확히 반복되면 앞 발화 구간을 컷(filler처럼 keeps에서 subtract). 자막은 drop_words_in_spans로 잘린 앞 발화 단어 제거해 영상-자막 동기화. 단어 1개 반복·의도한 강조·정상 발화는 안 건드림(오탐 최소화). 부분 더듬·말바꿈은 자동컷 안 하고 NG 표시(임계값 0.85→0.8). 합성+실제영상 검증(오탐 0). snap+subtract 순서로 반복 구간 정상 제거 확인.
- 자막/무음 튜닝 3건. (1) 무음 더 공격적: 기본 min_silence 0.5→0.3, pad 0.2→0.1(단어 잘림은 snap이 막음), '쉼 감도' 슬라이더 0.1~1.2로 확장(서버 클램프 0.1). 실제영상 60.3→30.6s 컷, 끝잘림 0건. (2) 자막 1줄: TextStyle auto_wrapping=False(type=text). (3) 자막 끝 마침표 제거(?,!는 유지).
- 자막 가짜 목록번호 제거. whisper가 목록 모드에 갇혀 narration에도 5,5,6,7… 번호를 붙이는 환각 대응(script_edit.strip_list_numbers). 실제 목록은 1부터 증가하는 연속 → 시퀀스 이탈 번호는 가짜로 보고 앞 'N.' 제거, narration 나오면 1로 리셋. 진짜 6(증상#6) vs 가짜 6(narration 뒤) 구분 케이스까지 실제 자막으로 검증. 자막 빌드(build_draft_from_keeps)에 적용.

## 2026-05-31

- 배포 호환성 수정. 가족 맥(시스템 Python 3.9.6)에서 install.command 실패(deps는 3.10+ 필요). install.command가 python3.13~3.10 탐지, 없으면 Homebrew로 python@3.13 설치 후 그 인터프리터로 venv 생성(이전 실패 venv는 rm). 추가로 bash 스크립트에서 brew가 안 보이는 문제(기본 셸 zsh, brew PATH가 ~/.zprofile에만) → /opt/homebrew/bin/brew shellenv 직접 소싱. README에 ZIP 격리(Gatekeeper) 해결법(xattr -dr) 추가. Dock 런처 .app(커스텀 아이콘) 생성은 로컬 전용(.gitignore).

## 2026-05-30

- 버그 수정(유효 구간 끝 잘림). 무음 검출이 단어의 약한 끝소리(받침·조사 '가/을/를')를 무음으로 잘못 잡아 말이 끝나기 전 잘리는 문제. ASR 단어 타임스탬프로 보존 구간이 단어 중간을 자르지 않게 끝/시작을 단어 경계까지 확장(script_edit.snap_keeps_to_words), 잔말 단어는 제외. 실제 영상(60s)에서 끝잘림 9건→0건, 빌드(비디오15+자막8) 정상. 라이브·슬라이더 재분석 양쪽 적용.
- 1차 완성(status done). 로드맵 Step0~5단 + 배포까지 완료, 사용자 캡컷 확인 OK. 이후는 실사용 피드백 기반 개선. 공유: github.com/dawon1982/capcutai (애플 실리콘 맥 설치형). 실행은 run.command 더블클릭.
- uploads 자동정리(디스크 누적 방지). 빌드 성공 직후 해당 업로드 삭제(미디어는 드래프트 폴더로 하드링크 반입돼 안전) + 잡 소비, 서버 시작 시 이전 세션 잔여 업로드 일괄 정리. 샘플 영상 samples/demo_ko.mp4 추가(설치자 체험용). in-process로 시작정리·빌드후삭제·하드링크 생존·잡404 검증.
- 버그 수정(실제 녹화 영상 0초/빌드 실패). ffprobe 컨테이너 길이(예 60.326s)가 pycapcut이 읽는 실제 소재 길이(60.193s)보다 길어, 마지막 보존 구간이 소재 끝을 넘으면 VideoSegment가 ValueError로 크래시 → draft_content.json 미생성 → 캡컷 0초. app/draft.py build_jumpcut_draft에서 material.duration으로 보존 구간 클램프. 실제 .mov(60s, 1620x1080)로 재현·수정 검증(비디오23+자막8, draft_info 생성). TTS 합성 클립은 컨테이너=스트림 길이라 안 터졌던 케이스.
- 피드백 반영(말 끝 잘림). 패딩 기본값 0.15→0.2s. 검토 화면에 '말 끝 여유'(pad) 슬라이더 추가 — '쉼 감도'와 함께 /api/reanalyze로 즉시 재분석. in-process(pad 0/0.2/0.4 → 보존 12.5/13.5/14.5s)·브라우저 검증, 콘솔 무에러.
- 배포(설치형 공유). 애플 실리콘 맥 지인용: requirements.txt(의존성 고정), install.command(ffmpeg·venv·모델 자동), run.command(서버+브라우저), README. 임시 venv(Python 3.13)로 requirements 완전성·mlx_whisper import 검증. GitHub Public 푸시: github.com/dawon1982/capcutai. (참고: mlx-whisper는 애플 실리콘 전용이라 Vercel/클라우드 배포 불가 — 로컬 설치형으로 결정.)
- 5단 완료(브라우저 검증). 분석(무음→ASR→잔말)과 드래프트 빌드를 분리: 처리 후 항상 '검토 화면'(원본 영상 플레이어 + 타임라인 + 보존구간 목록). [/] 키로 보존구간 추가, delete로 삭제, 타임라인 클릭 seek, NG 막대 원클릭 제거. '드래프트 만들기'로 사용자 확정 keeps 빌드(/api/build). 영상은 /api/video Range로 서빙. 말끝 잘림 대응: compute_keep_segments에 패딩(0.15s)으로 단어 끝소리·호흡 보존, 최소무음 0.3→0.5s. '쉼 감도' 슬라이더(/api/reanalyze, ASR 재실행 없이 무음만 재검출+잔말 유지). preview MCP로 [/]·delete·NG제거·슬라이더·빌드 전 흐름 + 결과 keeps 일치 검증, 콘솔 무에러.
- 4단 완료. app/script_edit.py: 잔말(음/어 등) 단어 타임스탬프로 자동 컷 — whisper 끝 타임스탬프가 짧게 끊겨 트레일링 소리가 남는 문제를 '다음 단어 시작까지' 잘라 해결. NG(반복 문장)는 인접 세그먼트 유사도로 검출해 표시만(자동 컷 안 함). 자막에서도 잔말 단어 제거. 결과 카드에 대본 전문+NG 목록 노출(브라우저 스크린샷 검증). 캡컷 함정 추가 해결(app/draft.py _stage_media): 캡컷은 샌드박스라 컨테이너 밖 원본을 못 읽어 '파일 액세스 불가' → 미디어를 드래프트 폴더 안으로 하드링크(복사비용0)로 반입. 잔말 컷+자막 캡컷 재생 직접 검증 통과.
- 3단 완료. mlx-whisper(large-v3-turbo)로 한국어 전사(세그먼트+단어, 내용해시 캐시, asyncio.Lock 직렬화 — numba 동시호출 segfault 방지). ASR 세그먼트를 점프컷 타임라인에 매핑(컷 구간은 보존 경계로 스냅)해 자막 트랙(흰 글자+검은 외곽선, 하단) 추가. 한국어 TTS 검증 클립(16.7s→13.75s, 무음2/세그3) → 캡컷에서 자막 재생 직접 검증 통과.
- 2단 완료. FastAPI(app/server.py) + 정적 HTML 1장(app/static/index.html) + 비동기 파이프라인(app/pipeline.py). 드래그앤드롭 업로드 → SSE 스테퍼(무음→ASR→잔말→드래프트). asr/filler는 아직 stub. 디자인: 다크 모노+그린 1색. 포트 8770(8765는 대시보드가 점유). 백엔드 curl + 브라우저 실제 SSE→DOM + 스크린샷으로 검증.
- 1단 완료. ffmpeg silencedetect로 무음 검출 → pycapcut으로 점프컷 드래프트 생성. 합성 클립(8.5s→6.0s) 캡컷 8.2.0에서 직접 재생 검증 통과.
- 캡컷 8.2.0 함정 2건 해결(app/draft.py _finalize_draft): pycapcut가 draft_meta_info.json의 tm_duration을 0으로 둬서 00:00/재생불가 → 실제 길이 패치. 신버전 캡컷은 draft_info.json을 읽어 → draft_content.json 복사본 생성. pycapcut 시간단위는 µs이고 float은 이미 µs로 해석됨(초→µs 직접 변환 필요).
- 초기화: 환경 점검, python3.11 venv, pycapcut 0.0.3 설치.
