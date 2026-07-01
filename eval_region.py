# -*- coding: utf-8 -*-
"""지역 해소 회귀 게이트 — '지도는 찍히는데 방역은 못 잡는' 비대칭을 막는다.

배경(2026-06-30): "광화문에서 러브버그 발견" → 지도는 광화문 좌표를 찍지만, 방역은
시군구를 못 잡아 관할 보건소를 못 줬다. 원인은 ① 광화문이 룰 레이어에 없었고
② geocode 캐시가 '좌표만 있고 행정구역 없는' 항목이었으며 ③ 오프라인에서 좌표→시군구
다리가 없었기 때문. 이 게이트는 같은 유형이 다시 생기는지 assert 로 강제한다.

오프라인(KAKAO 키 없이) 통과해야 한다. 모델 로드 불필요(룰·데이터만).
실행:  ..\\.venv\\Scripts\\python.exe eval_region.py
"""
import json
from pathlib import Path

import region_detect as RD
from recommend import recommend
from region_resolve import resolve_region
from offices_db import coarse_cities

GEOCODE = Path(__file__).resolve().parent / "web" / "data" / "geocode.json"

# (문장, 기대 시군구) — 룰 레이어가 오프라인으로 잡아야 하는 핵심 랜드마크
RULE_CASES = [
    ("광화문에서 러브버그 발견", "종로구"),
    ("명동에 모기 많아요", "중구"),
    ("이태원 바퀴벌레 나왔어요", "용산구"),
    ("강남에 러브버그 너무 많아요", "강남구"),
    ("해운대에 말벌집 생겼어요", "해운대구"),
    ("수원역에서 모기 물렸어요", "수원시"),
]

# 잡담은 지역 None 이어야 한다(과매칭 방지)
NONE_CASES = ["오늘 점심 뭐먹지", "날씨 좋네요"]


def main():
    fails = []

    # 1) 핵심 랜드마크: 룰 레이어가 시군구를 잡고, 방역이 보건소까지 연결되어야 함
    for text, exp_sigungu in RULE_CASES:
        r = RD.detect_region(text)
        if r.get("sigungu") != exp_sigungu:
            fails.append(f"detect_region: {text!r} → {r.get('sigungu')} (기대 {exp_sigungu})")
        reg = resolve_region(text)
        rec = recommend("lovebug", True, "dispatch",
                        reg.get("sigungu") or "", reg.get("sido") or "")
        if not rec.get("office"):
            fails.append(f"방역 보건소 미연결: {text!r} (region={reg})")
        print(f"O  {text}  → {r.get('sigungu')} / {rec.get('office', {}).get('name', '—')}")

    # 2) 잡담은 지역 None
    for text in NONE_CASES:
        r = RD.detect_region(text)
        if r.get("sigungu") or r.get("sido"):
            fails.append(f"과매칭: {text!r} → {r}")

    # 2.5) 거친 시(구 가진 일반시) 처리:
    #   - offices.json 의 'X시 Y구' 패턴에서 거친 시 집합이 도출돼야 한다(천안/수원 등).
    #   - 거친 시는 룰만으로 short-circuit 되면 구가 빠져 관할을 못 잡으므로, region_resolve 가
    #     좌표로 구까지 정밀화해야 한다(온라인). 오프라인(이 게이트)에선 룰 시로 폴백하되
    #     보건소는 연결돼야 한다(아무 것도 못 주는 것보다 낫게).
    coarse = coarse_cities()
    for must in ("천안시", "수원시", "용인시"):
        if must not in coarse:
            fails.append(f"거친 시 미도출: {must} ∉ coarse_cities() (offices.json 형식 확인)")
    reg = resolve_region("천안에 모기 많아요")          # 랜드마크 없음 → 오프라인 폴백
    rec = recommend("lovebug", True, "dispatch",
                    reg.get("sigungu") or "", reg.get("sido") or "")
    if not rec.get("office"):
        fails.append(f"거친 시 폴백 보건소 미연결: 천안 (region={reg})")

    # 3) 캐시 불변식: 좌표가 있으면 최소 시도는 있어야 한다(좌표만 있는 항목 금지)
    cache = json.loads(GEOCODE.read_text(encoding="utf-8"))
    bare = [k for k, v in cache.items()
            if isinstance(v, dict) and v.get("lat") is not None
            and not v.get("sido") and not v.get("sigungu")]
    if bare:
        fails.append(f"좌표만 있고 행정구역 없는 캐시 항목 {len(bare)}개: {bare[:10]}")

    print()
    assert not fails, "회귀 발생:\n  - " + "\n  - ".join(fails)
    print(f"[GATE] 지역 해소 회귀 0 — 랜드마크 {len(RULE_CASES)}건 + 캐시 불변식 통과 ✅")


if __name__ == "__main__":
    main()
