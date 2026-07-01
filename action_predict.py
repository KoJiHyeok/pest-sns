"""action 분류 추론 모듈 (CONTRACTS 계약①).

train_action.py 가 만든 3개 산출물(models/action_*)을 읽어
한글 문장 → action(emergency·dispatch·guide·none) + 확률을 돌려준다.

전처리는 pest 모델과 '똑같아야' 하므로 tokenize 를 predict.py 에서 import 한다
(학습 train_action.py 도 같은 tokenize 를 쓴다 — 셋이 어긋나면 조용히 망가짐).
"""
import json
from pathlib import Path

import numpy as np

import warnings
warnings.filterwarnings("ignore")
import tensorflow as tf  # noqa: E402

from predict import tokenize  # noqa: E402  ← pest 모델과 동일 전처리 재사용(필수)

MODEL_DIR = Path(__file__).parent / "models"
SEQ_LEN = 32
MAX_TOKENS = 2000

LABELS = ["emergency", "dispatch", "guide", "none"]


def load_action():
    """models/action_vocab.json + action_label_map.json + action_model.tflite 로드.

    반환: (vectorizer, interp, label_map) — predict.load() 와 동일 패턴.
    """
    vocab = json.loads((MODEL_DIR / "action_vocab.json").read_text(encoding="utf-8"))
    label_map = json.loads((MODEL_DIR / "action_label_map.json").read_text(encoding="utf-8"))

    # 학습 때와 동일한 전처리 레이어를 vocab 으로 복원.
    # vocab[0]='', vocab[1]='[UNK]' 는 레이어가 자동 복원하므로 실제 토큰만 전달.
    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=MAX_TOKENS,
        output_mode="int",
        output_sequence_length=SEQ_LEN,
        standardize=None,
        split="whitespace",
    )
    vectorizer.set_vocabulary(vocab[2:])

    interp = tf.lite.Interpreter(model_path=str(MODEL_DIR / "action_model.tflite"))
    interp.allocate_tensors()
    return vectorizer, interp, label_map


def predict_action(text, vectorizer, interp, label_map):
    """문장 1개 → {"action": "<LABELS 중 1>", "probs": {"emergency":.., ...}}."""
    tokenized = tokenize(text)
    x = vectorizer([tokenized]).numpy().astype("int32")  # (1, 32)

    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]
    interp.set_tensor(inp["index"], x)
    interp.invoke()
    probs = interp.get_tensor(out["index"])[0]  # (클래스수,)

    idx = int(np.argmax(probs))
    action = label_map[str(idx)]
    probs_by_label = {label_map[str(i)]: float(probs[i]) for i in range(len(label_map))}
    return {"action": action, "probs": probs_by_label}


if __name__ == "__main__":
    L = load_action()
    for t in [
        "단국대 천안캠퍼스에 말벌집이 생겼어요",   # emergency
        "러브버그 너무 많아요",                    # dispatch
        "모기 어떻게 없애요?",                     # guide
        "오늘 날씨 좋네요",                        # none
    ]:
        r = predict_action(t, *L)
        top = sorted(r["probs"].items(), key=lambda p: -p[1])[:3]
        top_s = ", ".join(f"{k}={v:.2f}" for k, v in top)
        print(f"[{r['action']:9s}] {t}\n    {top_s}")
