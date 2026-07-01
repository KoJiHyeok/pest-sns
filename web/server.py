"""해충 제보 웹앱 — Flask.

디자인 목업을 실제 동작으로: 입력 → /api/predict(진짜 tflite 모델) → 결과 + 예방카드.
지도(/map)는 좌표 데이터가 없어 아직 정적 목업이다.

실행 (pest-sns 폴더에서):
    ../.venv/Scripts/python.exe web/server.py
    → http://127.0.0.1:8600
"""
import collections
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # pest-sns/
sys.path.insert(0, str(ROOT))

import load_env  # noqa: E402,F401  (.env → os.environ; KAKAO 키 읽기 전에 먼저)

import predict as P  # noqa: E402  (predict.py 재사용)
import advisory  # noqa: E402  (이음새 보정 단일 출처 — chat_app.py와 공유)
from region_detect import detect_region  # noqa: E402  (시도/시군구 추출 재사용)
from flask import Flask, jsonify, render_template, request  # noqa: E402

PEST_INFO = json.loads((ROOT / "pest_info.json").read_text(encoding="utf-8"))
DATA = ROOT / "web" / "data"
REPORTS_PATH = DATA / "reports.json"
USER_REPORTS_PATH = DATA / "user_reports.json"
GEOCODE_PATH = DATA / "geocode.json"
LEVEL_RANK = {"low": 1, "mid": 2, "high": 3}
KAKAO_JS_KEY = os.environ.get("KAKAO_JS_KEY", "").strip()
KAKAO_REST_KEY = os.environ.get("KAKAO_REST_KEY", "").strip()
HANGUL_RE = re.compile(r"[가-힣]")
LOCATION_CLEAN_RE = re.compile(
    r"(에서|근처에서|주변에서|앞에서|뒤에서|안에서|인근에서|에|근처|주변|앞|뒤|안|인근|부근|쪽)$"
)
# 건물 표면·실내 위치어(창문/벽/천장…)는 '장소'가 아니라 해충이 '어디에' 붙었는지다.
# 장소 쿼리에 남으면 Kakao 키워드 검색이 엉뚱한 상호(예: '벽과 창문' 창호집)에 매칭된다.
# 긴 단어가 먼저 매칭되도록 길이순으로 둔다.
SURFACE_RE = re.compile(
    r"\s*(?:창문틀|창문|창틀|유리창|방충망|모기장|벽면|천장|천정|바닥|"
    r"문틈|문틀|현관문|현관|베란다|발코니|테라스|옥상|지붕|처마|"
    r"화장실|욕실|주방|부엌|싱크대|배수구|하수구|환풍구|에어컨|"
    r"침대|이불|옷장|서랍|책상|식탁|쓰레기통|화분|창|벽|문)$"
)
PEST_TERMS = ("러브버그", "바퀴벌레", "말벌", "진드기", "빈대", "모기")
REPORT_ACTION_RE = re.compile(
    r"(출몰|발견|신고|방역|나왔|나와|많|떼|붙|날아다|보였|봤|있|생겼|불편|무섭|조심)"
)

app = Flask(__name__)

# 모델은 서버 시작 시 1회만 로드 (무거움)
print("모델 로딩 중...")
VEC, INTERP, LABEL_MAP = P.load()
print("모델 로드 완료.")

# ── 방역 도우미 통합 (Phase2 모듈 재사용, graceful) ──────────────────────────
#   "AI로 분석" → pest 분류 + action + (지오코딩으로) 관할 보건소 + 대응 가이드
try:
    import action_predict as AP  # noqa: E402

    ACTION_MODEL = AP.load_action()
except Exception as _e:
    AP, ACTION_MODEL = None, None
    print("action 모델 없음 — 방역 도우미 action 비활성:", _e)
try:
    import region_detect as RD  # noqa: E402
except Exception:
    RD = None
try:
    from recommend import recommend as build_recommend  # noqa: E402
except Exception:
    build_recommend = None
try:
    from offices_db import coarse_cities  # noqa: E402  (구 가진 거친 시 집합 — region_resolve와 동일)
except Exception:
    coarse_cities = lambda: set()


def read_json_body():
    """JSON 요청을 명시적으로 디코딩한다.

    브라우저 fetch는 UTF-8을 쓰지만, Windows 로컬 테스트 도구가 charset 없이
    CP949 바이트를 보내는 경우가 있어 한글 입력이 모델까지 깨져 도달할 수 있다.
    """
    raw = request.get_data(cache=True)
    if raw:
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                return json.loads(raw.decode(encoding))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
    return request.get_json(silent=True) or {}


def looks_garbled_korean(text):
    compact = "".join(str(text).split())
    if not compact or HANGUL_RE.search(compact):
        return False
    question_marks = compact.count("?")
    return question_marks >= 3 and question_marks / len(compact) >= 0.3


def read_json_file(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


_SEED_REPORTS = None  # 불변 시드(reports.json, 5만행) 메모리 캐시 — 기동 시 1회만 파싱


def seed_reports():
    """reports.json 은 런타임에 안 바뀌는 가상 시드(5만행, 8.6MB) → 1회 파싱 후 재사용.

    예전엔 매 요청마다 8.6MB를 다시 파싱했다(/api/reports GET·POST·raw 전부).
    서버 재시작 시 다시 로드된다(시드 파일이 바뀌면 재시작 필요 — 문서상 불변).
    """
    global _SEED_REPORTS
    if _SEED_REPORTS is None:
        _SEED_REPORTS = read_json_file(REPORTS_PATH, [])
    return _SEED_REPORTS


def load_reports():
    # 시드(캐시) + 사용자 제보(작음, 매번 최신). 연결은 새 list 라 캐시 원본은 안 건드린다.
    return seed_reports() + read_json_file(USER_REPORTS_PATH, [])


def load_geocode():
    return read_json_file(GEOCODE_PATH, {})


def normalize_location_key(location):
    return re.sub(r"\s+", "", str(location).strip())


def clean_location(raw):
    loc = re.sub(r"\s+", " ", str(raw)).strip(" ,.!?~…")
    # 절 연결어미(…인데/…이고/…라서) 뒤는 다른 절 → 장소가 아니므로 잘라낸다.
    #   "호서대학교 천안캠퍼인데 창문" → "호서대학교 천안캠퍼"
    loc = re.sub(r"(인데|이고|이라서|라서|이며|이라|인데요|구요|는데)\s+\S.*$", "", loc).strip(" ,.!?~…")
    while True:
        nxt = LOCATION_CLEAN_RE.sub("", loc).strip(" ,.!?~…")
        nxt = SURFACE_RE.sub("", nxt).strip(" ,.!?~…")
        if nxt == loc:
            break
        loc = nxt
    loc = re.sub(r"^(오늘|방금|지금|아까|어제)\s+", "", loc).strip()
    return loc if len(normalize_location_key(loc)) >= 2 else ""


def extract_location(text, pest_en=None):
    """문장에서 해충명 앞에 나온 장소 후보를 추출한다."""
    normalized = P.normalize_text(text)
    hits = [(normalized.find(term), term) for term in PEST_TERMS if normalized.find(term) >= 0]
    if hits:
        idx, _ = min(hits, key=lambda pair: pair[0])
        loc = clean_location(normalized[:idx])
        if loc:
            return loc

    match = re.search(r"(.+?)(?:에서|에|근처|주변|앞|뒤|안|인근|부근)\s*" + REPORT_ACTION_RE.pattern, normalized)
    if match:
        return clean_location(match.group(1))
    return None


def region_from_name(name):
    """장소명 → {"sido","sigungu"} (룰 레이어, 오프라인). 못 잡으면 빈 값."""
    if RD is None or not name:
        return {}
    r = RD.detect_region(name) or {}
    return {k: r.get(k) for k in ("sido", "sigungu") if r.get(k)}


def cache_geocode(location, coord):
    """좌표를 캐시에 적재. 좌표만 쓰면 지도는 되지만 방역(시군구)은 못 잡으므로,
    이름에서 룰로 시도/시군구를 함께 적재해 '좌표만 있고 행정구역 없는' 항목을 만들지 않는다."""
    cache = load_geocode()
    keys = {location, normalize_location_key(location)}
    if coord.get("resolved_location"):
        keys.add(coord["resolved_location"])
        keys.add(normalize_location_key(coord["resolved_location"]))
    # 좌표→행정구역: 키 있으면 정밀(coord2regioncode), 없으면 이름 룰로 보강(오프라인)
    region = kakao_regioncode(coord["lat"], coord["lng"]) or {}
    if not region.get("sigungu"):
        region = region_from_name(location) or region_from_name(coord.get("resolved_location")) or region
    for key in keys:
        if key:
            entry = {"lat": float(coord["lat"]), "lng": float(coord["lng"])}
            if region.get("sido"):
                entry["sido"] = region["sido"]
            if region.get("sigungu"):
                entry["sigungu"] = region["sigungu"]
            cache[key] = entry
    write_json_file(GEOCODE_PATH, cache)


def geocode_kakao(query):
    if not KAKAO_REST_KEY:
        return None
    url = "https://dapi.kakao.com/v2/local/search/keyword.json?query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {KAKAO_REST_KEY}"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        docs = json.load(resp).get("documents", [])
    if not docs:
        return None
    doc = docs[0]
    return {
        "lat": float(doc["y"]),
        "lng": float(doc["x"]),
        "resolved_location": doc.get("place_name") or query,
        "display_name": doc.get("address_name") or doc.get("road_address_name") or "",
        "source": "kakao",
    }


def geocode_nominatim(query):
    url = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=3&q=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "pest-sns-local-demo/1.0 (local geocoding for user reports)",
            "Accept-Language": "ko,en",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        docs = json.load(resp)
    if not docs:
        return None
    doc = docs[0]
    return {
        "lat": float(doc["lat"]),
        "lng": float(doc["lon"]),
        "resolved_location": doc.get("name") or query,
        "display_name": doc.get("display_name", ""),
        "source": "nominatim",
    }


def geocode_location(location):
    cache = load_geocode()
    compact = normalize_location_key(location)
    for key in (location, compact):
        if key in cache:
            entry = cache[key]
            return {
                "lat": float(entry["lat"]),
                "lng": float(entry["lng"]),
                "resolved_location": key,
                "source": "cache",
                "sido": entry.get("sido"),
                "sigungu": entry.get("sigungu"),
            }

    compact_query = normalize_location_key(location)
    queries = [location]
    if compact_query and compact_query != location:
        queries.append(compact_query)
    if "천안" not in location and ("두정" in location or "도서관" in location):
        queries.append(f"{location} 천안")
        if compact_query and compact_query != location:
            queries.append(f"{compact_query} 천안")
    queries.append(f"{location} 대한민국")

    last_error = None
    for query in dict.fromkeys(queries):
        for provider in (geocode_kakao, geocode_nominatim):
            try:
                coord = provider(query)
                if coord:
                    coord["query"] = query
                    cache_geocode(location, coord)
                    return coord
                time.sleep(0.1)
            except Exception as exc:
                last_error = str(exc)
                continue
    return {"error": last_error or "location_not_found"}


def kakao_regioncode(lat, lng):
    """좌표 → 행정구역(시도/시군구). Kakao coord2regioncode. 키 없으면 None."""
    if not KAKAO_REST_KEY:
        return None
    url = ("https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"
           f"?x={lng}&y={lat}")
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


def cache_region(location, coord, rc):
    """해소된 시군구를 geocode 캐시에 적재 → 다음부터 오프라인."""
    cache = load_geocode()
    keys = {location, normalize_location_key(location), coord.get("resolved_location")}
    for key in keys:
        if not key:
            continue
        entry = cache.get(key) or {"lat": float(coord["lat"]), "lng": float(coord["lng"])}
        entry["sido"] = rc.get("sido")
        entry["sigungu"] = rc.get("sigungu")
        cache[key] = entry
    write_json_file(GEOCODE_PATH, cache)


def resolve_region(text, pest_en):
    """text → (sido, sigungu, source).
       1) region_detect 룰(오프라인) → 2) 장소구절 지오코딩 → 좌표 → 시군구(캐시/Kakao)."""
    sido = sigungu = None
    if RD is not None:
        r = RD.detect_region(text)
        sido, sigungu = r.get("sido"), r.get("sigungu")
    # 룰이 구 없는 '천안시' 같은 거친 시까지만 잡았으면 short-circuit 하지 않고
    # 좌표로 구까지 정밀화한다(실패 시 룰 값 폴백). 이름에 박힌 지역보다 좌표가 진실.
    if sigungu and sigungu not in coarse_cities():
        return sido, sigungu, "rule"

    loc = extract_location(text, pest_en)
    if loc:
        coord = geocode_location(loc)
        if not coord.get("error") and coord.get("lat") is not None:
            cached_sgg = coord.get("sigungu")
            # 캐시 시군구가 정밀(구 포함)하면 그대로. 거친 시(용인시 등)면 좌표로 구까지 정밀화.
            if cached_sgg and cached_sgg not in coarse_cities():
                return coord.get("sido") or sido, cached_sgg, "geocode-cache"
            rc = kakao_regioncode(coord["lat"], coord["lng"])
            if rc and rc.get("sigungu"):
                cache_region(loc, coord, rc)               # 적재(다음부턴 오프라인)
                return rc.get("sido") or sido, rc["sigungu"], "geocode"
            if cached_sgg:                                 # 정밀화 실패(오프라인) → 거친 캐시 유지
                return coord.get("sido") or sido, cached_sgg, "geocode-cache"
    # 정밀화 실패: 룰이 거친 시라도 잡았으면 유지.
    return sido, sigungu, "rule" if sigungu else "none"


def build_advisory(text, pest_en):
    """방역 도우미 결과: action + 관할 보건소 + 대응 가이드. 모듈 없으면 None."""
    if AP is None or build_recommend is None:
        return None
    action = AP.predict_action(text, *ACTION_MODEL).get("action", "none")
    # 이음새 보정 ①②(단일 출처 advisory) — chat_app.py와 같은 규칙.
    #   여긴 pest≠none 으로만 들어와 ①은 자동 비활성, ②(none→dispatch)만 적용된다.
    pest_en, _is_real, action = advisory.correct_seam(text, pest_en, action)
    sido, sigungu, src = resolve_region(text, pest_en)
    res = build_recommend(pest_en, pest_en != "none", action, sigungu or "", sido or "")
    return {
        "action": action,
        "region": {"sido": sido, "sigungu": sigungu, "source": src},
        "office": res.get("office", {}),
        "reply": res.get("reply", ""),
        "headline": res.get("headline", ""),
        "steps": res.get("steps", []),
    }


def next_report_id(reports):
    ids = [r.get("id") for r in reports if isinstance(r.get("id"), int)]
    return (max(ids) if ids else 0) + 1


_MARKERS_CACHE = {"key": None, "value": None}


def _user_reports_key():
    """user_reports.json 의 (mtime, size) — 바뀌면 마커 캐시를 무효화하는 키.

    시드는 불변이라 마커 집계가 달라지는 유일한 원인은 사용자 제보(POST)뿐.
    그 파일이 그대로면 5만행 재집계를 건너뛰고 직전 결과를 그대로 돌려준다.
    """
    try:
        st = USER_REPORTS_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def build_markers():
    """지명별 집계 마커(none 제외, 좌표 있는 곳만). user_reports 가 안 바뀌면 캐시 재사용."""
    key = _user_reports_key()
    if _MARKERS_CACHE["key"] == key and _MARKERS_CACHE["value"] is not None:
        return _MARKERS_CACHE["value"]

    reports = load_reports()
    geo = load_geocode()

    by_loc = collections.defaultdict(list)
    for r in reports:
        if r["pest_label"] != "none":
            by_loc[r["location"]].append(r)

    out = []
    for loc, rs in by_loc.items():
        coord = geo.get(loc) or geo.get(normalize_location_key(loc))
        if not coord and rs and rs[0].get("lat") is not None and rs[0].get("lng") is not None:
            coord = {"lat": rs[0]["lat"], "lng": rs[0]["lng"]}
        if not coord:
            continue
        counts = collections.Counter(r["pest_label"] for r in rs)
        # 대표 해충 = 가장 많이 신고된 종 (색 다양성 ↑). 동률이면 더 위험한 종 우선.
        headline = max(counts, key=lambda p: (counts[p], LEVEL_RANK.get(PEST_INFO.get(p, {}).get("level", "low"), 0)))
        info = PEST_INFO.get(headline, {})
        out.append({
            "location": loc, "lat": coord["lat"], "lng": coord["lng"],
            "count": len(rs), "pest_en": headline, "pest_kr": P.KOR.get(headline, headline),
            "level": info.get("level", "low"), "hint": info.get("prevention", ""),
            "recent": min(r["minutes_ago"] for r in rs),
        })
    out.sort(key=lambda x: -x["count"])

    _MARKERS_CACHE["key"], _MARKERS_CACHE["value"] = key, out
    return out


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/map")
def map_page():
    return render_template("map.html", kakao_js_key=KAKAO_JS_KEY)


@app.route("/api/predict", methods=["POST"])
def api_predict():
    text = (read_json_body().get("text", "") or "").strip()
    if not text:
        return jsonify({"error": "문장을 입력하세요."}), 400
    if looks_garbled_korean(text):
        return jsonify({
            "error": "한글 입력이 깨져서 서버에 도착했습니다. UTF-8로 다시 전송해주세요.",
        }), 400

    en, kr, probs, order = P.predict(text, VEC, INTERP, LABEL_MAP)
    pairs = sorted(zip(order, probs), key=lambda pair: -pair[1])

    return jsonify({
        "text": text,
        "pest_en": en,
        "pest_kr": kr,
        "confidence": float(max(probs)),
        "probs": [{"en": o, "kr": P.KOR.get(o, o), "p": float(p)} for o, p in pairs],
        "info": PEST_INFO.get(en),
        "location_guess": extract_location(text, en) if en != "none" else None,
        "advisory": build_advisory(text, en) if en != "none" else None,
    })


@app.route("/api/reports/raw")
def api_reports_raw():
    return jsonify({
        "reports": load_reports(),
        "geocode": load_geocode(),
    })


@app.route("/api/reports", methods=["GET", "POST"])
def api_reports():
    """지명별로 제보를 집계 → 좌표 붙여 마커용 데이터 반환 (none 제외, 좌표 있는 곳만)."""
    if request.method == "POST":
        body = read_json_body()
        text = (body.get("text", "") or "").strip()
        pest_en = (body.get("pest_en", "") or "").strip()
        if not text:
            return jsonify({"error": "제보 문장이 없습니다."}), 400
        if not pest_en:
            pest_en, _, _, _ = P.predict(text, VEC, INTERP, LABEL_MAP)
        if pest_en == "none":
            return jsonify({"error": "해충 제보로 분류되지 않아 등록하지 않았습니다."}), 400

        location = clean_location(body.get("location") or "") or extract_location(text, pest_en)
        if not location:
            return jsonify({"error": "문장에서 위치를 찾지 못했습니다. 장소명을 함께 입력해주세요."}), 422

        coord = geocode_location(location)
        if coord.get("error"):
            # 정밀 장소명(랜드마크)이 안 잡히면 시도/시군구로 폴백 → 도시 중심에라도 핀.
            region = detect_region(text)
            region_q = " ".join(x for x in (region.get("sido"), region.get("sigungu")) if x)
            if region_q:
                alt = geocode_location(region_q)
                if not alt.get("error"):
                    coord = alt
                    location = region.get("sigungu") or region.get("sido") or location
        if coord.get("error"):
            return jsonify({"error": f"'{location}' 위치를 검색하지 못했습니다.", "detail": coord["error"]}), 422

        user_reports = read_json_file(USER_REPORTS_PATH, [])
        report_location = coord.get("resolved_location") or location
        report = {
            "id": next_report_id(load_reports()),
            "text": text,
            "pest_label": pest_en,
            "location": report_location,
            "location_input": location,
            "lat": float(coord["lat"]),
            "lng": float(coord["lng"]),
            "minutes_ago": 0,
            "source": "user",
        }
        user_reports.append(report)
        write_json_file(USER_REPORTS_PATH, user_reports)
        return jsonify({
            "ok": True,
            "report": report,
            "pest_kr": P.KOR.get(pest_en, pest_en),
            "geocode": coord,
        }), 201

    return jsonify(build_markers())


if __name__ == "__main__":
    # 로컬 기본값은 127.0.0.1:8600 그대로. 배포(HF Spaces 등)에서는 HOST/PORT 환경변수로 덮어쓴다.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8600"))
    app.run(host=host, port=port, debug=False)
