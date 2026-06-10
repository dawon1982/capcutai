import re
from difflib import SequenceMatcher

# 명백한 망설임 간투사만. "그/뭐/이제/저기"처럼 정상 단어로도 쓰이는 건
# 오탐(필요한 말 삭제) 위험이라 기본 제외. 필요하면 호출부에서 set을 넘겨 조정.
DEFAULT_FILLERS = {"음", "으음", "어", "어어", "아", "으", "엄", "흠"}

_PUNCT = re.compile(r"[\s.,!?…·\"'’”“\-~]+")


def _norm(text: str) -> str:
    return _PUNCT.sub("", text)


def find_filler_cuts(segments, fillers=None):
    """단어 타임스탬프에서 군말 구간 [(start, end)] 추출 (원본 시간).

    whisper의 단어 끝 타임스탬프가 실제 소리보다 짧게 끊기는 경우가 많아
    [filler.start, 다음 단어 시작]까지 잘라 트레일링 소리·공백까지 제거한다.
    """
    fillers = DEFAULT_FILLERS if fillers is None else fillers
    cuts = []
    for seg in segments:
        words = seg.get("words", [])
        for i, w in enumerate(words):
            if _norm(w["word"]) in fillers:
                end = words[i + 1]["start"] if i + 1 < len(words) else seg["end"]
                cuts.append((w["start"], max(w["end"], end)))
    return cuts


def strip_fillers(segments, fillers=None):
    """자막용: 각 세그먼트에서 군말 단어를 빼고 text를 재조합한 새 세그먼트 리스트."""
    fillers = DEFAULT_FILLERS if fillers is None else fillers
    out = []
    for seg in segments:
        words = [w for w in seg.get("words", []) if _norm(w["word"]) not in fillers]
        text = "".join(w["word"] for w in words).strip() if words else ""
        if not text:
            text = seg["text"]  # 단어 정보가 없으면 원문 유지
        out.append({**seg, "text": text, "words": words})
    return out


def find_repeat_cuts(segments, min_words: int = 2, max_words: int = 8):
    """즉시 반복되는 다단어 구절(말더듬·리테이크)의 '앞' 발화 구간 [(start, end)] 반환.

    예: '오늘도 이렇게 말씀하시는'이 바로 이어 반복되면 앞 것을 컷(뒤 발화는 남김).
    2단어 이상 '정확히' 일치하는 연속 반복만 대상 — 의도한 강조/단어 하나 반복은 건드리지 않음.
    """
    words = [w for s in segments for w in s.get("words", [])]
    norms = [_norm(w["word"]) for w in words]
    n = len(words)
    cuts = []
    i = 0
    while i < n:
        matched = False
        kmax = min(max_words, (n - i) // 2)
        for k in range(kmax, min_words - 1, -1):
            if norms[i:i + k] == norms[i + k:i + 2 * k] and all(norms[i:i + k]):
                cuts.append((words[i]["start"], words[i + k]["start"]))
                i += k  # 앞 발화만 컷, 뒤 발화 위치로 이동(3번 이상 반복도 연쇄 처리)
                matched = True
                break
        if not matched:
            i += 1
    return cuts


def drop_words_in_spans(segments, spans):
    """주어진 시간 구간(컷)에 시작이 걸친 단어를 빼고 자막 텍스트 재조합.
    반복 컷으로 잘려나간 앞 발화가 자막에 남지 않게 한다(영상-자막 동기화)."""
    if not spans:
        return segments
    out = []
    for seg in segments:
        ws = seg.get("words", [])
        if not ws:
            out.append(seg)
            continue
        kept = [w for w in ws if not any(cs <= w["start"] < ce for cs, ce in spans)]
        text = "".join(w["word"] for w in kept).strip()
        out.append({**seg, "text": text, "words": kept})
    return out


def find_ng_candidates(segments, threshold: float = 0.8):
    """인접 세그먼트 텍스트가 비슷하면 재촬영(NG) 의심 → 앞 테이크를 후보로 표시.

    컷하지 않고 '제안'만. {start, end, text, similarity}.
    """
    cands = []
    for i in range(len(segments) - 1):
        a, b = segments[i], segments[i + 1]
        na, nb = _norm(a["text"]), _norm(b["text"])
        if not na or not nb:
            continue
        sim = SequenceMatcher(None, na, nb).ratio()
        if sim >= threshold:
            cands.append({
                "start": a["start"],
                "end": a["end"],
                "text": a["text"],
                "similarity": round(sim, 2),
            })
    return cands


def _merge(regions):
    regions = sorted([s, e] for s, e in regions if e > s)
    out = []
    for s, e in regions:
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


_LEAD_NUM = re.compile(r"^\s*(\d+)[.)]\s+")
_NUM_ONLY = re.compile(r"^\d+$")


def _drop_lead_number_words(words, num: str):
    """앞쪽 단어 토큰들이 목록 번호('5.' 등)를 이루면 그 토큰들을 제거."""
    acc = ""
    for i, w in enumerate(words):
        acc += _norm(w["word"])
        if acc == num:
            return words[i + 1:]
        if not num.startswith(acc):
            break
    return words


def strip_list_numbers(segments):
    """whisper가 자동으로 붙인 가짜 목록 번호 제거(자막용).

    실제 목록은 1부터 1씩 증가하는 연속 번호. 그 시퀀스를 벗어나는 번호는 가짜로 보고
    앞 'N.' 마커를 텍스트와 단어 토큰 양쪽에서 제거(텍스트-단어 동기화 유지).
    번호 없는 문장(narration)이 나오면 시퀀스를 리셋(새 목록은 다시 1부터).
    숫자만 남은 세그먼트('20' 등 점 없는 반복 환각)는 통째로 비움.
    """
    out = []
    expected = 1  # 다음에 와야 할 '진짜' 번호 (1부터 시작)
    for seg in segments:
        text = seg["text"]
        words = seg.get("words", [])
        m = _LEAD_NUM.match(text)
        if not m:
            expected = 1  # narration → 새 목록 대기
            t = text
        elif int(m.group(1)) == expected:
            expected += 1  # 연속 증가 → 실제 목록 항목, 번호 유지
            t = text
        else:
            expected = -1  # 시퀀스 이탈 → narration 리셋 전까지 이후 번호도 가짜
            t = _LEAD_NUM.sub("", text, count=1)
            words = _drop_lead_number_words(words, m.group(1))
        if _NUM_ONLY.match(_norm(t)):  # 숫자만 남은 환각 세그먼트('20' 등) 제거
            t, words = "", []
        if t == text and words is seg.get("words", []):
            out.append(seg)
        else:
            out.append({**seg, "text": t, "words": words})
    return out


def snap_keeps_to_words(keeps, words, fillers=None, margin: float = 0.05):
    """보존 구간 경계가 단어(잔말 제외) 중간을 자르지 않게 단어 끝/시작까지 확장.

    무음 검출이 단어의 약한 끝소리(받침·조사 '가/을/를' 등)를 무음으로 잘못 잡으면
    말이 끝나기 전에 잘린다. ASR 단어 타임스탬프로 이런 잘림을 보정한다.
    잔말 단어는 일부러 자르므로 보호 대상에서 제외.
    """
    fillers = DEFAULT_FILLERS if fillers is None else fillers
    spans = sorted(
        (w["start"], w["end"]) for w in words if _norm(w["word"]) not in fillers
    )
    out = []
    for ks, ke in keeps:
        nks, nke = ks, ke
        for ws, we in spans:
            if ks <= ws < nke < we:        # 단어가 keep 안에서 시작해 끝을 넘김 → 끝 확장
                nke = we + margin
            elif ws < nks < we <= ke:      # 단어가 keep 시작 전 시작 → 시작 당김
                nks = max(0.0, ws - margin)
        out.append([nks, nke])
    return _merge(out)


def subtract_cuts(keeps, cuts, min_keep: float = 0.2):
    """보존 구간에서 컷 구간을 빼고 남는 [(s, e)] 반환. min_keep 미만 조각은 버림."""
    merged = _merge(cuts)
    if not merged:
        return keeps
    result = []
    for ks, ke in keeps:
        cursor = ks
        for cs, ce in merged:
            if ce <= cursor or cs >= ke:
                continue
            if cs - cursor >= min_keep:
                result.append((cursor, cs))
            cursor = max(cursor, ce)
            if cursor >= ke:
                break
        if ke - cursor >= min_keep:
            result.append((cursor, ke))
    return result
