"""정적 사이트 빌드 — Flask 백엔드 없이 Cloudflare Pages에 올릴 수 있게 굽는다.

서버가 하던 일을 빌드 타임 / 브라우저로 옮긴다:
  - /api/predict  → 브라우저 추론(infer.js + data/model.json). 이 파일은 안 건드림.
  - /api/reports  → 여기서 markers.json 으로 미리 집계(정적).
  - render_template → 정적 html (url_for 제거).

실행 (pest-sns 폴더에서):
    ../.venv/Scripts/python.exe web/build_static.py
출력: web/site/  (이 폴더를 Cloudflare Pages 루트로 배포)
"""
import collections
import json
import shutil
from pathlib import Path

WEB = Path(__file__).resolve().parent      # pest-sns/web
ROOT = WEB.parent                          # pest-sns
SITE = WEB / "site"
DATA_OUT = SITE / "data"
STATIC_OUT = SITE / "static"
DATA_IN = WEB / "data"

LEVEL_RANK = {"low": 1, "mid": 2, "high": 3}
KOR = {
    "none": "해충 없음", "lovebug": "러브버그", "mosquito": "모기",
    "cockroach": "바퀴벌레", "bedbug": "빈대", "wasp": "말벌",
    "hornet": "장수말벌", "termite": "흰개미", "ant": "개미",
    "fire_ant": "불개미", "fly": "파리", "tick": "진드기",
    "stink_bug": "노린재", "aphid": "진딧물", "unknown": "미확인 해충",
}


def build_markers(pest_info):
    """server.py 의 /api/reports 집계를 그대로 정적 JSON 으로."""
    reports = json.loads((DATA_IN / "reports.json").read_text(encoding="utf-8"))
    geo_path = DATA_IN / "geocode.json"
    geo = json.loads(geo_path.read_text(encoding="utf-8")) if geo_path.exists() else {}

    by_loc = collections.defaultdict(list)
    for r in reports:
        if r["pest_label"] != "none":
            by_loc[r["location"]].append(r)

    out = []
    for loc, rs in by_loc.items():
        coord = geo.get(loc)
        if not coord:
            continue
        counts = collections.Counter(r["pest_label"] for r in rs)
        headline = max(counts, key=lambda p: (LEVEL_RANK.get(pest_info.get(p, {}).get("level", "low"), 0), counts[p]))
        info = pest_info.get(headline, {})
        out.append({
            "location": loc, "lat": coord["lat"], "lng": coord["lng"],
            "count": len(rs), "pest_en": headline, "pest_kr": KOR.get(headline, headline),
            "level": info.get("level", "low"), "hint": info.get("prevention", ""),
            "recent": min(r["minutes_ago"] for r in rs),
        })
    out.sort(key=lambda x: -x["count"])
    return out


def main():
    SITE.mkdir(parents=True, exist_ok=True)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    STATIC_OUT.mkdir(parents=True, exist_ok=True)

    pest_info = json.loads((ROOT / "pest_info.json").read_text(encoding="utf-8"))
    (DATA_OUT / "pest_info.json").write_text(json.dumps(pest_info, ensure_ascii=False), encoding="utf-8")

    markers = build_markers(pest_info)
    (DATA_OUT / "markers.json").write_text(json.dumps(markers, ensure_ascii=False), encoding="utf-8")

    shutil.copy2(WEB / "static" / "styles.css", STATIC_OUT / "styles.css")

    print(f"markers: {len(markers)} locations")
    print(f"site → {SITE}")
    for p in sorted(SITE.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(SITE)}  ({p.stat().st_size} B)")


if __name__ == "__main__":
    main()
