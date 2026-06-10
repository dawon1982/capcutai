"""컷·자막 핵심 로직 회귀 테스트 (ASR 불필요, 수 초 내 완료).

실행: .venv/bin/python tests/test_core.py
알려진 문제 패턴(말더듬·조사 끝·쉼·환각·용어 오인식)이 코드 수정 후에도
계속 잡히는지 확인한다. 실패하면 AssertionError로 즉시 중단.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.draft import captions_to_srt, compute_captions  # noqa: E402
from app.script_edit import (  # noqa: E402
    apply_glossary,
    compute_keeps_from_words,
    find_filler_cuts,
    find_ng_candidates,
    find_repeat_cuts,
    refine_keeps_with_vad,
    strip_list_numbers,
    subtract_cuts,
)


def W(t, s, e):
    return {"word": t, "start": s, "end": e}


PASS = 0


def ok(cond, name):
    global PASS
    assert cond, f"FAIL: {name}"
    PASS += 1
    print("  ✓", name)


# ── 컷: 단어 간격 기반 보존 구간 ──────────────────────────────
words = [W(" 안녕하세요", 0.0, 0.8), W(" 반갑습니다", 1.0, 1.8), W(" 다음", 3.0, 3.4)]
keeps = compute_keeps_from_words(words, 10.0, 0.3, 0.1)
ok(len(keeps) == 2, "0.3s 넘는 단어 간격만 컷")
ok(all(not (ks <= w["start"] < ke and w["end"] > ke + 0.01)
       for ks, ke in keeps for w in words), "보존 구간이 단어를 끝까지 포함")

# VAD 보정: 실제 음성 꼬리가 단어 끝보다 길면 연장(한도 max_adjust 내),
# 단어 끝 근처에 VAD 정보가 없으면 무보정(보수적)
vad = [(0.0, 2.3), (2.9, 3.9)]
refined = refine_keeps_with_vad(keeps, words, vad, 0.1, 0.6)
ok(all(b - a > 0 for a, b in refined), "VAD 보정 후 구간 유효")
ok(abs(refined[0][1] - 2.4) < 0.05, "꼬리 연장은 단어끝+max_adjust 한도에서 멈춤")
ok(refine_keeps_with_vad(keeps, words, [(0.0, 1.0)], 0.1, 0.6)[0][1] == keeps[0][1],
   "단어 끝 근처에 VAD 정보 없으면 무보정")

# ── 잔말·반복 ────────────────────────────────────────────────
segs = [{"start": 0, "end": 4, "text": "음 오늘도 이렇게 오늘도 이렇게 좋아요", "words": [
    W(" 음", 0.0, 0.2), W(" 오늘도", 0.5, 0.9), W(" 이렇게", 0.9, 1.3),
    W(" 오늘도", 1.5, 1.9), W(" 이렇게", 1.9, 2.3), W(" 좋아요", 2.5, 3.0)]}]
ok(find_filler_cuts(segs)[0][0] == 0.0, "잔말(음) 검출")
rc = find_repeat_cuts(segs)
ok(len(rc) == 1 and abs(rc[0][0] - 0.5) < 0.01, "즉시 반복은 앞 테이크만 컷")
ok(subtract_cuts([(0.0, 4.0)], rc, 0.2)[0][1] <= 1.5, "반복 구간이 keeps에서 빠짐")

# ── 용어 사전 교정 ───────────────────────────────────────────
g = apply_glossary(
    [{"start": 0, "end": 1, "text": "잣말과 굿말과 사과", "words": []}],
    ["잔말", "군말", "무음"])
ok("잔말" in g[0]["text"] and "군말" in g[0]["text"], "잣말→잔말, 굿말→군말(자모 최근접)")
ok("사과" in g[0]["text"], "무관 단어는 교정 안 함")

# ── 가짜 목록번호 ────────────────────────────────────────────
nums = strip_list_numbers([
    {"start": 0, "end": 1, "text": "1. 첫째", "words": []},
    {"start": 1, "end": 2, "text": "2. 둘째", "words": []},
    {"start": 2, "end": 3, "text": "내용 설명", "words": []},
    {"start": 3, "end": 4, "text": "2. 가짜 번호", "words": []},
    {"start": 4, "end": 5, "text": "20", "words": []},
])
ok(nums[0]["text"].startswith("1.") and nums[1]["text"].startswith("2."), "실제 순차 번호 유지")
ok(not nums[3]["text"].startswith("2."), "시퀀스 이탈 번호 제거")
ok(nums[4]["text"] == "", "맨숫자 환각 세그먼트 비움")

# ── NG 후보 ──────────────────────────────────────────────────
ng = find_ng_candidates([
    {"start": 0, "end": 2, "text": "같은 문장을 말해요", "words": []},
    {"start": 3, "end": 5, "text": "같은 문장을 말해요", "words": []}])
ok(len(ng) == 1 and ng[0]["alt_start"] == 3, "NG 앞/뒤 테이크 시각 포함")

# ── 자막(캡션) ───────────────────────────────────────────────
seg = {"start": 0, "end": 9, "text": "", "words": [
    W(" 천천히", 0.0, 2.0), W(" 말합니다", 2.2, 4.0),
    W(" 그리고", 4.2, 4.5), W(" 빠르게", 4.5, 4.8), W(" 말해요", 4.8, 5.1),
    W(" 마지막", 5.3, 5.6), W(" 문장입니다.", 5.6, 6.2)]}
seg["text"] = "".join(w["word"] for w in seg["words"]).strip()
caps = compute_captions([seg], [(0.0, 9.0)])
ok(all(len(t) <= 16 for t, a, b in caps), "캡션 16자 이하")
ok(all(not t.rstrip().endswith(".") for t, a, b in caps), "캡션 끝 마침표 없음")
ok(abs(caps[0][1] - 0.0) < 0.01, "캡션 시작 = 실제 단어 발화 시각")
ok(all(caps[i][1] <= caps[i + 1][1] for i in range(len(caps) - 1)), "캡션 시간 정렬")
# 기계적 16자 분할이면 '…그리고 빠르게'에서 끊김 — 어미(고) 경계에서 끊겨야 함
ok(caps[0][0].endswith("그리고") and caps[1][0] == "빠르게 말해요",
   "어미 경계에서 자연 분할(기계적 글자수 분할 아님)")

srt = captions_to_srt(caps)
ok(srt.startswith("1\n00:00:00,000 --> "), "SRT 형식")

print(f"\nALL PASS ({PASS}건)")
