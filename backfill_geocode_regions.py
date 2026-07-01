# -*- coding: utf-8 -*-
"""geocode.json 의 '좌표만 있고 행정구역(시도/시군구) 없는' 항목을 룰 레이어로 보강한다.

배경: 지도(8600)의 cache_geocode 가 과거엔 좌표만 적재했다. 그래서 지도는 점을 찍지만
방역(시군구 필요)은 같은 장소를 못 잡는 비대칭이 생겼다(예: '광화문'). cache_geocode 는
이제 행정구역을 함께 적재하지만, 이미 쌓인 좌표-only 항목은 이 스크립트로 한 번 보강한다.

방식: 각 항목의 '이름'에 region_detect.detect_region 을 돌려 시도/시군구를 얻고,
**찾았을 때만** 적재한다(추측 0 — 못 찾으면 그대로 둠). 좌표→행정구역 추론(센트로이드)은
경계 근처에서 틀릴 수 있어 쓰지 않는다. 멱등(여러 번 돌려도 안전). git 으로 되돌릴 수 있다.

실행:  ..\\.venv\\Scripts\\python.exe backfill_geocode_regions.py [--write]
       --write 없으면 dry-run(무엇이 바뀌는지만 출력).
"""
import json
import sys
from pathlib import Path

import region_detect as RD

GEOCODE = Path(__file__).resolve().parent / "web" / "data" / "geocode.json"


def main(write):
    cache = json.loads(GEOCODE.read_text(encoding="utf-8"))
    filled_sigungu = filled_sido = 0
    still_bare = []
    for name, entry in cache.items():
        if not isinstance(entry, dict) or entry.get("lat") is None:
            continue
        if entry.get("sigungu"):
            continue  # 이미 시군구 있음
        r = RD.detect_region(name) or {}
        sido, sigungu = r.get("sido"), r.get("sigungu")
        if sigungu:
            entry["sigungu"] = sigungu
            filled_sigungu += 1
        if sido and not entry.get("sido"):
            entry["sido"] = sido
            if not sigungu:
                filled_sido += 1
        if not entry.get("sido") and not entry.get("sigungu"):
            still_bare.append(name)

    print(f"항목 {len(cache)}개 / 시군구 보강 {filled_sigungu} · 시도만 보강 {filled_sido}")
    if still_bare:
        print(f"여전히 미해소(이름만으로는 행정구역 불명) {len(still_bare)}개:",
              ", ".join(still_bare[:20]) + (" ..." if len(still_bare) > 20 else ""))
    if write:
        GEOCODE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {GEOCODE}")
    else:
        print("(dry-run — 실제 저장하려면 --write)")


if __name__ == "__main__":
    main("--write" in sys.argv)
