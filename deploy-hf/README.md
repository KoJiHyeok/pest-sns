---
title: 해충 제보 데모
emoji: 🐛
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
short_description: 한국어 문장 → 해충 분류 + 예방 가이드 (Kiwi 형태소 + TFLite)
---

# 해충 제보 데모

한국어 제보 문장을 입력하면 **Kiwi 형태소 분석 → TFLite 텍스트 분류**로 해충 종류를 판별하고
예방 가이드를 보여준다. 지도(`/map`)는 Kakao JavaScript 키를 넣으면 지역별 제보 마커를 표시한다.

- **추론**: `predict.py` (kiwipiepy 형태소 토큰화 + `pest_text_model.tflite`)
- **서버**: `web/server.py` (Flask) — `POST /api/predict`, `GET /api/reports`
- 엣지(Cloudflare 등)에선 TensorFlow·Kiwi 가 안 돌아 Python 호스트(여기)에서 구동.

## 지도 키 설정

Space Settings → Variables and secrets 에서 `KAKAO_JS_KEY` 변수에 Kakao JavaScript 키를 넣으면
방문자가 키를 입력하지 않아도 `/map`에서 지도가 자동으로 열린다.

Kakao Developers 의 JavaScript SDK 도메인에는 Space 의 실제 앱 도메인
`https://<계정>-<space-name>.hf.space` 를 등록해야 한다.

> 원본 레포: Second-Brain-Project / Hoseo / pest-sns. 모델 재학습 후엔 `deploy-hf/deploy.py` 로 재배포.
