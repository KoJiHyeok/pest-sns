"""지명 → 좌표 (Kakao 로컬 REST API). 'REST API 키' 용도 데모.

환경변수 KAKAO_REST_KEY 가 필요하다. reports.json 의 지명들을 키워드 검색해
web/data/geocode.json 에 병합 저장한다. (이미 있는 지명은 건너뜀)
전체를 API로 다시 받으려면 geocode.json 을 지우고 실행.

PowerShell:
  $env:KAKAO_REST_KEY="여기에_REST_API_키"
  ..\.venv\Scripts\python.exe geocode.py
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "web" / "data"
REPORTS = DATA / "reports.json"
OUT = DATA / "geocode.json"
KEY = os.environ.get("KAKAO_REST_KEY")


def geocode(loc):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json?query=" + urllib.parse.quote(loc)
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {KEY}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        docs = json.load(resp).get("documents", [])
    if not docs:
        return None
    return {"lat": float(docs[0]["y"]), "lng": float(docs[0]["x"])}


def main():
    if not KEY:
        print("환경변수 KAKAO_REST_KEY 가 없습니다.")
        print('PowerShell:  $env:KAKAO_REST_KEY="REST_API_키"  후 다시 실행')
        sys.exit(1)
    reports = json.loads(REPORTS.read_text(encoding="utf-8"))
    locs = sorted({r["location"] for r in reports if r.get("location")})
    cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    added = 0
    for loc in locs:
        if loc in cache:
            continue
        try:
            c = geocode(loc)
            if c:
                cache[loc] = c
                added += 1
                print(f"OK   {loc} -> {c['lat']:.4f}, {c['lng']:.4f}")
            else:
                print(f"미발견 {loc}")
            time.sleep(0.2)
        except Exception as e:
            print(f"실패 {loc}: {e}")
    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT}  (총 {len(cache)}곳, 신규 {added})")


if __name__ == "__main__":
    main()
