# 해충 제보 데모 — Hugging Face Spaces (Docker SDK)
# Flask 앱(web/server.py)을 그대로 실행한다. 추론은 Kiwi(형태소)+TensorFlow tflite 라
# Cloudflare 같은 엣지에선 못 돌고, 여기서 Python 으로 그대로 돈다.
FROM python:3.11-slim

# tensorflow/kiwipiepy 휠은 manylinux 라 빌드툴 불필요. OpenMP 런타임(libgomp)만 보강.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Spaces 는 컨테이너 포트 7860 을 외부로 노출. server.py 가 HOST/PORT 환경변수를 읽는다.
ENV HOST=0.0.0.0 \
    PORT=7860 \
    HF_HOME=/app/.cache
EXPOSE 7860

CMD ["python", "web/server.py"]
