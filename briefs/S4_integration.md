# S4 — 통합: chat_app.py (조이너)

너는 방역 추천 에이전트의 **S4(통합) 세션**이다. `CONTRACTS.md`를 읽고 계약①②③을 모두 따른다.
너는 **마지막에 실물을 꿰매는 조이너**다. S1·S2가 STATUS에서 ✅ 뜨기 전엔 mock으로 골격만 잡는다.
작업 디렉토리: `Hoseo/pest-sns`. **소유 파일은 `chat_app.py` 하나** — 기존 `web/server.py`는 안 건드린다.

## 목표
새 Flask 앱(**포트 8700**)이 챗 페이지를 서빙하고, 두 모델 + 추천을 엮어 계약③ `/chat`을 구현.

## 골격 (mock 단계부터 작성 가능)
```python
# chat_app.py
from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path
import predict as P                 # 기존 pest 모델 (재사용)
# import action_predict as A        # S1 done 후 주석 해제
# from recommend import recommend   # S2 done 후 주석 해제

ROOT = Path(__file__).parent
app = Flask(__name__)
_pest = None; _act = None

def _ensure():
    global _pest, _act
    if _pest is None: _pest = P.load()
    # if _act is None: _act = A.load_action()

@app.route("/")
def index():
    return send_from_directory(ROOT / "web" / "static", "chat.html")

@app.route("/chat", methods=["POST"])
def chat():
    _ensure()
    msg = (request.get_json() or {}).get("message", "")
    pest_en, pest_kor, probs, order = P.predict(msg, *_pest)
    # action = A.predict_action(msg, *_act)["action"]   # S1 후
    # res = recommend(pest_en, pest_en != "none", action, "")  # S2 후
    # mock fallback (S1·S2 전):
    action = "emergency" if pest_en == "wasp" else ("none" if pest_en=="none" else "dispatch")
    res = {"reply": f"[demo] {pest_kor}/{action}", "office": {}}
    return jsonify({"reply": res["reply"], "pest": pest_en,
                    "action": action, "office": res.get("office", {})})

if __name__ == "__main__":
    app.run(port=8700, debug=True)
```
- `chat.html`/`chat.js`/`chat.css`는 S3 소유 — 그대로 `web/static`에서 서빙. `chat.js`의 `MOCK`을 `false`로
  바꾸는 것도 S4가 연결 시점에(S3과 합의) 처리.
- S1·S2 ✅ 뜨면 위 주석 3줄 해제하고 mock fallback 제거.

## DONE 체크 (최종 E2E — 오프라인)
```bash
python chat_app.py   # 다른 터미널
# 브라우저 localhost:8700 → 3 시나리오:
#   "단국대 천안캠퍼스에 말벌집이 생겼어요"  → wasp/emergency + 보건소/119
#   "러브버그 너무 많아요"                    → lovebug/dispatch or guide
#   "오늘 날씨 좋네요"                        → none, 안내 멘트
```
망 차단 상태에서도 도는지 확인(외부 다운로드 0). 통과하면 STATUS `S4 ✅ localhost:8700 E2E 3시나리오 정상`.
막히면 `S4 ⛔ <사유>`.
