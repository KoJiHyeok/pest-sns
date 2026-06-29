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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # pest-sns/
sys.path.insert(0, str(ROOT))

import predict as P  # noqa: E402  (predict.py 재사용)
from flask import Flask, jsonify, render_template, request  # noqa: E402

PEST_INFO = json.loads((ROOT / "pest_info.json").read_text(encoding="utf-8"))
DATA = ROOT / "web" / "data"
LEVEL_RANK = {"low": 1, "mid": 2, "high": 3}
KAKAO_JS_KEY = os.environ.get("KAKAO_JS_KEY", "").strip()
HANGUL_RE = re.compile(r"[가-힣]")

app = Flask(__name__)

# 모델은 서버 시작 시 1회만 로드 (무거움)
print("모델 로딩 중...")
VEC, INTERP, LABEL_MAP = P.load()
print("모델 로드 완료.")


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
    })


@app.route("/api/reports")
def api_reports():
    """지명별로 제보를 집계 → 좌표 붙여 마커용 데이터 반환 (none 제외, 좌표 있는 곳만)."""
    reports = json.loads((DATA / "reports.json").read_text(encoding="utf-8"))
    geo_path = DATA / "geocode.json"
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
    return jsonify(out)


if __name__ == "__main__":
    # 로컬 기본값은 127.0.0.1:8600 그대로. 배포(HF Spaces 등)에서는 HOST/PORT 환경변수로 덮어쓴다.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8600"))
    app.run(host=host, port=port, debug=False)
