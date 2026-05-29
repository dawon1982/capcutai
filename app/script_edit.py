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


def find_ng_candidates(segments, threshold: float = 0.85):
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
