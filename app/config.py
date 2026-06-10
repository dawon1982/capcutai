import json
import os

from app.script_edit import DEFAULT_FILLERS

PATH = os.path.join(os.path.dirname(__file__), "..", "settings.json")

DEFAULTS = {
    "glossary": [],                       # 용어 사전(받아쓰기 교정 + ASR 힌트)
    "fillers": sorted(DEFAULT_FILLERS),   # 자동 컷할 잔말 단어
    "precision": False,                   # 고정밀 모델(large-v3, 느림) 사용 여부
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(PATH) as f:
            data = json.load(f)
        for k, v in DEFAULTS.items():
            if k in data and type(data[k]) is type(v):
                cfg[k] = data[k]
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


def save(cfg: dict) -> None:
    with open(PATH, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
