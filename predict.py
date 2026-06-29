"""해충 분류 추론 모듈.

train_to_tflite.py가 만든 3개 산출물(models/)을 읽어
한글 문장 → 해충 클래스 + 확률을 돌려준다.

핵심: .tflite 모델은 '숫자(토큰) → 확률'만 한다. 한글 문장을 숫자로 바꾸는
전처리는 여기서 학습 때와 '똑같이' 재현해야 한다(vocab.json으로 복원).
"""
import json
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
import tensorflow as tf  # noqa: E402

MODEL_DIR = Path(__file__).parent / "models"
SEQ_LEN = 32
MAX_TOKENS = 2000

# 영문 클래스명 → 한글 (label_map은 영문만 담고 있어 표시용으로 매핑)
KOR = {
    "none": "해충 없음", "lovebug": "러브버그", "mosquito": "모기",
    "cockroach": "바퀴벌레", "bedbug": "빈대", "wasp": "말벌",
    "hornet": "장수말벌", "termite": "흰개미", "ant": "개미",
    "fire_ant": "불개미", "fly": "파리", "tick": "진드기",
    "stink_bug": "노린재", "aphid": "진딧물", "unknown": "미확인 해충",
}


def load():
    """모델·사전·라벨맵을 한 번 로드한다 (앱에서 캐싱해 재사용)."""
    vocab = json.loads((MODEL_DIR / "vocab.json").read_text(encoding="utf-8"))
    label_map = json.loads((MODEL_DIR / "label_map.json").read_text(encoding="utf-8"))

    # 학습 때와 동일한 전처리 레이어를 vocab으로 복원.
    # vocab[0]='', vocab[1]='[UNK]' 는 레이어가 자동으로 다시 붙이므로 실제 토큰만 전달.
    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=MAX_TOKENS,
        output_mode="int",
        output_sequence_length=SEQ_LEN,
        standardize="lower_and_strip_punctuation",
    )
    vectorizer.set_vocabulary(vocab[2:])

    interp = tf.lite.Interpreter(model_path=str(MODEL_DIR / "pest_text_model.tflite"))
    interp.allocate_tensors()
    return vectorizer, interp, label_map


def predict(text, vectorizer, interp, label_map):
    """문장 1개 → (영문라벨, 한글, 확률[클래스순], 라벨순서리스트)."""
    x = vectorizer([text]).numpy().astype("int32")  # (1, 32)

    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]
    interp.set_tensor(inp["index"], x)
    interp.invoke()
    probs = interp.get_tensor(out["index"])[0]  # (클래스수,)

    idx = int(np.argmax(probs))
    en = label_map[str(idx)]
    order = [label_map[str(i)] for i in range(len(label_map))]
    return en, KOR.get(en, en), probs, order


if __name__ == "__main__":
    # 빠른 검증: 학습셋에 있던 문장으로 토큰화·추론이 맞게 도는지 확인
    vec, interp, lm = load()
    tests = [
        "수원역에서 말벌 때문에 불편합니다",   # 기대: wasp
        "오늘 날씨가 좋네요",                  # 기대: none
        "여의도공원에서 모기 때문에 불편합니다",  # 기대: mosquito
    ]
    for t in tests:
        en, kor, probs, order = predict(t, vec, interp, lm)
        top = sorted(zip(order, probs), key=lambda p: -p[1])[:3]
        top_s = ", ".join(f"{o}={p:.2f}" for o, p in top)
        print(f"[{en:9s} / {kor}]  ← {t}")
        print(f"    상위3: {top_s}")
