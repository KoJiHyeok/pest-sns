"""action 분류기 학습 (train_to_tflite.py 복사 — 라벨/경로/출력만 action 용으로 변경).

모델 구조(Embedding+GAP)·SEQ_LEN·tokenize 는 pest 모델과 '똑같이' 유지한다.
바뀐 것:
  - DATA_PATH      : data/action_data.csv
  - 라벨 컬럼      : pest_label → action
  - 출력 파일명    : action_model.tflite / action_vocab.json / action_label_map.json

실행:  ../.venv/Scripts/python.exe train_action.py
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import tensorflow as tf

from predict import tokenize  # 추론(action_predict)과 '똑같은' 형태소 토큰화를 공유

DATA_PATH = Path("data/action_data.csv")
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)

MAX_TOKENS = 2000
SEQ_LEN = 32        # pest 모델과 동일(전처리 일치가 생명)
EPOCHS = 80
SEED = 42

tf.random.set_seed(SEED)


def main():
    df = pd.read_csv(DATA_PATH)
    df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)

    labels = sorted(df["action"].unique().tolist())
    label_to_lid = {label: i for i, label in enumerate(labels)}

    y = df["action"].map(label_to_lid).astype("int32").values
    texts = [tokenize(t) for t in df["text"].astype(str)]

    # 클래스 불균형 보정(guide 가 적으므로 가중치 ↑)
    counts = np.bincount(y, minlength=len(labels))
    class_weight = {i: len(y) / (len(labels) * counts[i]) for i in range(len(labels))}

    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=MAX_TOKENS,
        output_mode="int",
        output_sequence_length=SEQ_LEN,
        standardize=None,
        split="whitespace",
    )
    vectorizer.adapt(texts)
    x = vectorizer(texts).numpy().astype("int32")

    model = tf.keras.Sequential([
        tf.keras.Input(shape=(SEQ_LEN,), dtype="int32", name="tokens"),
        tf.keras.layers.Embedding(MAX_TOKENS, 32, mask_zero=True),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dense(len(labels), activation="softmax", name="action_class"),
    ])
    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    model.fit(x, y, epochs=EPOCHS, batch_size=32, validation_split=0.2,
              class_weight=class_weight, verbose=1)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()

    (MODEL_DIR / "action_model.tflite").write_bytes(tflite_model)

    vocab = vectorizer.get_vocabulary()
    (MODEL_DIR / "action_vocab.json").write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (MODEL_DIR / "action_label_map.json").write_text(
        json.dumps({str(v): k for k, v in label_to_lid.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"완료: {len(labels)}개 action 클래스 학습 → "
          "models/action_model.tflite, models/action_vocab.json, models/action_label_map.json 생성")


if __name__ == "__main__":
    main()
