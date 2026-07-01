# -*- coding: utf-8 -*-
"""지역 해소 공용 모듈 — 자유 텍스트 → {"sido","sigungu","source"}.

  1) region_detect 룰 매칭(오프라인)으로 시군구가 잡히면 그대로.
  2) 못 잡으면: 문장에서 장소구절 추출 → (캐시/Kakao keyword) 좌표 →
     Kakao coord2regioncode → 시군구. 결과 시군구는 geocode.json 캐시에 적재해
     다음부터 오프라인으로 해소된다.

chat_app(8700)·web/server(8600)가 공유한다. 2번 라이브 해소는 KAKAO_REST_KEY 필요.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

import predict as P  # normalize_text 재사용 (학습 전처리와 동일 정규화)

try:
    from region_detect import detect_region
except Exception:
    detect_region = None

try:
    from offices_db import coarse_cities
except Exception:
    coarse_cities = lambda: set()

ROOT = Path(__file__).resolve().parent
GEOCODE_PATH = ROOT / "web" / "data" / "geocode.json"
KAKAO_REST_KEY = os.environ.get("KAKAO_REST_KEY", "").strip()

PEST_TERMS = ("러브버그", "바퀴벌레", "말벌", "진드기", "빈대", "모기")
_ACTION = (r"(출몰|발견|신고|방역|나왔|나와|많|떼|붙|날아다|보였|봤|있|생겼|불편|무섭|조심|출연)")
_CLEAN_TAIL = re.compile(
    r"(에서|근처에서|주변에서|앞에서|뒤에서|안에서|인근에서|에|근처|주변|앞|뒤|안|인근|부근|쪽)$"
)
# 건물 표면·실내 위치어(창문/벽/천장…)는 장소가 아니라 '어디에' 붙었는지다.
# 쿼리에 남으면 Kakao 키워드 검색이 엉뚱한 상호('벽과 창문' 등)에 매칭된다.
# web/server.py SURFACE_RE 와 동기화할 것.
_SURFACE = re.compile(
    r"\s*(?:창문틀|창문|창틀|유리창|방충망|모기장|벽면|천장|천정|바닥|"
    r"문틈|문틀|현관문|현관|베란다|발코니|테라스|옥상|지붕|처마|"
    r"화장실|욕실|주방|부엌|싱크대|배수구|하수구|환풍구|에어컨|"
    r"침대|이불|옷장|서랍|책상|식탁|쓰레기통|화분|창|벽|문)$"
)


def _norm_key(s):
    return re.sub(r"\s+", "", str(s).strip())


def _load_cache():
    if GEOCODE_PATH.exists():
        return json.loads(GEOCODE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache):
    GEOCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEOCODE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _clean_loc(raw):
    loc = re.sub(r"\s+", " ", str(raw)).strip(" ,.!?~…")
    while True:
        nxt = _CLEAN_TAIL.sub("", loc).strip(" ,.!?~…")
        nxt = _SURFACE.sub("", nxt).strip(" ,.!?~…")
        if nxt == loc:
            break
        loc = nxt
    loc = re.sub(r"^(오늘|방금|지금|아까|어제)\s+", "", loc).strip()
    return loc if len(_norm_key(loc)) >= 2 else ""


def extract_place(text):
    """문장에서 해충명 앞 장소 후보를 추출 (web/server.py extract_location과 동일 규칙)."""
    t = P.normalize_text(text)
    hits = [(t.find(term), term) for term in PEST_TERMS if t.find(term) >= 0]
    if hits:
        idx, _ = min(hits, key=lambda pair: pair[0])
        loc = _clean_loc(t[:idx])
        if loc:
            return loc
    m = re.search(r"(.+?)(?:에서|에|근처|주변|앞|뒤|안|인근|부근)\s*" + _ACTION, t)
    if m:
        return _clean_loc(m.group(1))
    return None


def _kakao_keyword(query):
    """장소명 → 좌표 (Kakao keyword search). 키 없으면 None."""
    if not KAKAO_REST_KEY:
        return None
    url = "https://dapi.kakao.com/v2/local/search/keyword.json?query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {KAKAO_REST_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            docs = json.load(resp).get("documents", [])
    except Exception:
        return None
    if not docs:
        return None
    d = docs[0]
    return {"lat": float(d["y"]), "lng": float(d["x"])}


def _kakao_regioncode(lat, lng):
    """좌표 → 행정구역(시도/시군구). Kakao coord2regioncode. 키 없으면 None."""
    if not KAKAO_REST_KEY:
        return None
    url = f"https://dapi.kakao.com/v2/local/geo/coord2regioncode.json?x={lng}&y={lat}"
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {KAKAO_REST_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            docs = json.load(resp).get("documents", [])
    except Exception:
        return None
    if not docs:
        return None
    doc = next((d for d in docs if d.get("region_type") == "H"), docs[0])
    return {"sido": doc.get("region_1depth_name"), "sigungu": doc.get("region_2depth_name")}


def resolve_region(text):
    """text → {"sido","sigungu","source"}. source: rule|geocode-cache|geocode|none."""
    sido = sigungu = None
    if detect_region is not None:
        r = detect_region(text)
        sido, sigungu = r.get("sido"), r.get("sigungu")
    # 룰이 구 없는 '천안시' 같은 거친 시까지만 잡았으면 short-circuit 하지 않고
    # 좌표로 구까지 정밀화한다(실패하면 아래에서 룰 값으로 폴백). 이름에 박힌 지역보다 좌표가 진실.
    if sigungu and sigungu not in coarse_cities():
        return {"sido": sido, "sigungu": sigungu, "source": "rule"}

    place = extract_place(text)
    if place:
        cache = _load_cache()
        entry = cache.get(place) or cache.get(_norm_key(place)) or {}
        cached_sgg = entry.get("sigungu")
        # 캐시 시군구가 정밀(구 포함)하면 그대로. 단 거친 시(용인시 등)면 short-circuit 하지 않고
        # 아래에서 좌표→구까지 정밀화한다(룰 경로와 같은 불변식 — 캐시도 예외 아님).
        if cached_sgg and cached_sgg not in coarse_cities():
            return {"sido": entry.get("sido") or sido, "sigungu": cached_sgg,
                    "source": "geocode-cache"}
        # 좌표 확보: 캐시 좌표 우선, 없으면 Kakao keyword
        lat = entry.get("lat")
        lng = entry.get("lng")
        if lat is None:
            kw = _kakao_keyword(place)
            if kw:
                lat, lng = kw["lat"], kw["lng"]
        if lat is not None:
            rc = _kakao_regioncode(lat, lng)
            if rc and rc.get("sigungu"):
                entry.update({"lat": lat, "lng": lng,
                              "sido": rc["sido"], "sigungu": rc["sigungu"]})
                cache[place] = entry
                cache[_norm_key(place)] = entry
                _save_cache(cache)
                return {"sido": rc.get("sido") or sido, "sigungu": rc["sigungu"],
                        "source": "geocode"}
        if cached_sgg:                                   # 정밀화 실패(오프라인) → 거친 캐시라도 유지
            return {"sido": entry.get("sido") or sido, "sigungu": cached_sgg,
                    "source": "geocode-cache"}
    # 정밀화 실패: 룰이 거친 시라도 잡았으면 그 값을 유지(아무 것도 못 주는 것보다 낫게).
    return {"sido": sido, "sigungu": sigungu, "source": "rule" if sigungu else "none"}


if __name__ == "__main__":
    for s in ["서울 코엑스에 말벌 출연", "강남에 모기 많아요",
              "해운대에 말벌집", "오늘 날씨 좋네요"]:
        print(f"{resolve_region(s)}  ← {s}")
