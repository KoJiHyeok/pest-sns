import json
from pathlib import Path
import numpy as np
import pandas as pd
import tensorflow as tf

from predict import tokenize  # 추론과 '똑같은' 한국어 형태소 토큰화를 공유

DATA_PATH = Path("sample_pest_sns.csv")
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)

MAX_TOKENS = 2000
SEQ_LEN = 32        # 원본의 SQL_LEN — SQL과 무관, '시퀀스 길이'라 SEQ_LEN으로 명확히
EPOCHS = 80         # [개선] 25 → 80 (데이터가 작아 경사 스텝이 적음)
SEED = 42

tf.random.set_seed(SEED)   # 재현성: 같은 데이터면 같은 결과


def main():
    df = pd.read_csv(DATA_PATH)
    # [개선] 행 셔플: validation_split은 '뒤쪽 20%'를 셔플 없이 가져가므로, CSV에 새 데이터를
    # 끝에 덧붙이면 검증셋이 특정 클래스로 쏠리고 그 행들이 학습에서 빠진다 → SEED 셔플로 방지.
    df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)

    # [FIX 1] CSV엔 'label' 컬럼이 없다. 라벨 컬럼은 'pest_label'.
    labels = sorted(df["pest_label"].unique().tolist())
    label_to_lid = {label: i for i, label in enumerate(labels)}

    y = df["pest_label"].map(label_to_lid).astype("int32").values
    # 추론과 동일하게 형태소 토큰화 후 공백으로 이어 둔다(아래 vectorizer는 공백 분리만).
    texts = [tokenize(t) for t in df["text"].astype(str)]

    # [개선] 클래스 불균형 보정: none(50%)으로 쏠리지 않게 해충 클래스 가중치를 높임
    counts = np.bincount(y, minlength=len(labels))
    class_weight = {i: len(y) / (len(labels) * counts[i]) for i in range(len(labels))}

    # standardize=None: 토큰화는 kiwi(tokenize)가 끝냈으므로 공백 분리만 한다.
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
        # [FIX 2] tf.keras.layers(...) 는 존재하지 않는 호출. 입력층은 tf.keras.Input.
        tf.keras.Input(shape=(SEQ_LEN,), dtype="int32", name="tokens"),
        # [개선] mask_zero=True: 패딩(0)을 평균 풀링에서 무시 → 실제 단어 신호 보존
        tf.keras.layers.Embedding(MAX_TOKENS, 32, mask_zero=True),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dense(len(labels), activation="softmax", name="pest_class"),
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

    # [FIX 4] 노션/app.py 기대 파일명은 pest_text_model.tflite (원본은 pest_model.tflite).
    (MODEL_DIR / "pest_text_model.tflite").write_bytes(tflite_model)

    vocab = vectorizer.get_vocabulary()
    (MODEL_DIR / "vocab.json").write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (MODEL_DIR / "label_map.json").write_text(
        json.dumps({str(v): k for k, v in label_to_lid.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"완료: {len(labels)}개 클래스 학습 → "
          "models/pest_text_model.tflite, models/vocab.json, models/label_map.json 생성")


# [FIX 3] 원본은 이 블록이 main() 안으로 들여쓰기돼 호출이 안 됐다. 모듈 최상단으로.
if __name__ == "__main__":
    main()
