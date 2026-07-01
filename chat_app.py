"""방역 추천 에이전트 — 챗 API (S4 통합, 독립 Flask 앱, 포트 8700).

흐름:  POST /chat {"message"} →
  ① pest 분류  (기존 predict.py + models/pest_text_model.tflite — 항상 사용)
  ② action 분류 (S1: action_predict.py — 있으면 사용, 없으면 pest 기반 mock)
  ③ 추천 결합  (S2: recommend.py + offices.json — 있으면 사용, 없으면 내장 fallback)
  → 계약③ JSON {"reply","pest","action","office"}

graceful import: S1·S2 산출물이 생기면 자동으로 실물을 쓴다(코드 수정 불필요).
기존 web/server.py(지도앱)는 건드리지 않는다.
"""
from pathlib import Path

import load_env  # noqa: F401  (.env → os.environ; region_resolve 가 KAKAO 키 읽기 전에 먼저)

from flask import Flask, jsonify, request, send_from_directory

import predict as P  # 기존 pest 모델 (검증 완료, 항상 사용)
import advisory  # 이음새 보정 단일 출처 (8600 분석앱과 공유)

ROOT = Path(__file__).parent
STATIC = ROOT / "web" / "static"

# ── S1 산출물 (action 모델) — 있으면 실물, 없으면 mock ───────────────────────
try:
    import action_predict as A  # noqa: F401

    _HAS_ACTION = True
except Exception:
    _HAS_ACTION = False

# ── S2 산출물 (추천 결합) — 있으면 실물, 없으면 내장 fallback ─────────────────
try:
    from recommend import recommend as _recommend

    _HAS_REC = True
except Exception:
    _HAS_REC = False

# ── 지역 해소 (룰 + 지오코딩 폴백) — 8600과 공유하는 region_resolve ──────────
try:
    from region_resolve import resolve_region as _resolve_region

    _HAS_REGION = True
except Exception:
    _HAS_REGION = False


# web/static 을 루트에서 서빙(chat.js·chat.css 가 / 기준 상대경로라 정적 route 필요).
app = Flask(__name__, static_folder=str(STATIC), static_url_path="")
_pest = None   # (vectorizer, interp, label_map)
_act = None    # action 모델 로드 캐시


def _ensure_loaded():
    global _pest, _act
    if _pest is None:
        _pest = P.load()
    if _HAS_ACTION and _act is None:
        _act = A.load_action()


def _mock_action(pest_en):
    """S1 없을 때 임시: pest 기반으로 그럴듯한 action 추정 (데모 끊김 방지용)."""
    if pest_en == "none":
        return "none"
    if pest_en == "wasp":
        return "emergency"
    return "dispatch"


def _fallback_recommend(pest_en, is_real, action, location=""):
    """S2(recommend.py) 없을 때 임시 응답. 실물이 생기면 이 함수는 안 쓰인다."""
    kor = P.KOR.get(pest_en, pest_en)
    if action == "none" or pest_en == "none":
        return {"reply": "해충 관련 내용이 아니에요. 상황(해충·장소)을 적어주시면 안내할게요.",
                "office": {}}
    tag = {"emergency": "[긴급]", "dispatch": "[신고]", "guide": "[정보]"}.get(action, "")
    return {"reply": f"{tag} {kor} 감지 (action={action}). "
                     f"[S2 recommend.py 연결 전 임시 응답]", "office": {}}


@app.route("/")
def index():
    if (STATIC / "chat.html").exists():
        return send_from_directory(STATIC, "chat.html")
    return ("chat.html (S3) 아직 없음. /chat API는 동작 중. "
            f"action={'real' if _HAS_ACTION else 'mock'}, "
            f"recommend={'real' if _HAS_REC else 'fallback'}"), 200


@app.route("/chat", methods=["POST"])
def chat():
    _ensure_loaded()
    msg = (request.get_json(silent=True) or {}).get("message", "").strip()
    if not msg:
        return jsonify({"reply": "메시지를 입력해주세요.", "pest": "none",
                        "action": "none", "office": {}})

    # ① pest
    pest_en, pest_kor, probs, order = P.predict(msg, *_pest)

    # ② action
    if _HAS_ACTION:
        action = A.predict_action(msg, *_act)["action"]
    else:
        action = _mock_action(pest_en)

    # 이음새 보정 ①②(단일 출처 advisory) — 8600 분석앱과 같은 규칙
    pest_en, is_real, action = advisory.correct_seam(msg, pest_en, action)

    # 지역 해소 (룰 → 지오코딩) → 시군구를 recommend에 주입(관할 보건소 룩업용)
    region = {"sido": None, "sigungu": None, "source": "off"}
    if _HAS_REGION:
        region = _resolve_region(msg)
    location = region.get("sigungu") or ""
    region_sido = region.get("sido") or ""

    # ③ 추천 결합
    if _HAS_REC:
        res = _recommend(pest_en, is_real, action, location, region_sido)
    else:
        res = _fallback_recommend(pest_en, is_real, action, location)

    return jsonify({
        "reply": res.get("reply", ""),
        "pest": pest_en,
        "action": action,
        "office": res.get("office", {}),
        "region": region,
    })


@app.route("/health")
def health():
    return jsonify({"ok": True,
                    "action": "real" if _HAS_ACTION else "mock",
                    "recommend": "real" if _HAS_REC else "fallback",
                    "region": "real" if _HAS_REGION else "off"})


if __name__ == "__main__":
    print(f"[chat_app] action={'real' if _HAS_ACTION else 'mock'}  "
          f"recommend={'real' if _HAS_REC else 'fallback'}")
    app.run(port=8700, debug=False)
