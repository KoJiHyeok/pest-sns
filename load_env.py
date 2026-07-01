# -*- coding: utf-8 -*-
"""로컬 .env 로더 (의존성 0). 진입점에서 가장 먼저 import 해야 한다.

목적: 운영(8600) env 와 동일하게 로컬에서도 KAKAO_REST_KEY / KAKAO_JS_KEY 를 쓰되,
키를 코드·채팅에 노출하지 않도록 gitignore 된 `.env` 파일에서 읽어 os.environ 에 넣는다.
이미 셸 env 에 있는 값은 덮어쓰지 않는다(셸 우선).

형식(.env):  KEY=VALUE  (한 줄 1개, # 주석·빈 줄 허용, 따옴표 선택)
오프라인 1급 제약과 무관 — 파일만 읽는다(네트워크 0). .env 없으면 조용히 통과.
"""
import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent / ".env"


def load(path=_ENV_PATH):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:   # 셸 env 우선
            os.environ[key] = val


load()
