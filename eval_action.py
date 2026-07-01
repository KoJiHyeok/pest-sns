"""action 모델을 '느낌'이 아니라 '숫자'로 검증하는 eval 하니스 (Phase2 E).

eval_holdout.py(pest) 스타일을 action 용으로. 핵심은 **정직한 홀드아웃**:
train_action.py 는 데이터를 seed=42 로 셔플한 뒤 `model.fit(validation_split=0.2)`
로 학습한다. Keras 의 validation_split 은 (셔플된) 배열의 **마지막 20%** 를 떼어
가중치 학습에서 제외한다 → 그 마지막 20% 가 '모델 가중치가 본 적 없는' 정직한 홀드아웃이다.
여기서 같은 셔플을 재현해 그 tail 을 평가셋으로 쓰고, train 과 **텍스트 교집합 0** 을 assert 한다.

실행:  ../.venv/Scripts/python.exe eval_action.py
"""
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path  # noqa: E402

import pandas as pd  # noqa: E402

import action_predict as A  # noqa: E402

# train_action.py 와 '똑같이' 맞춰야 홀드아웃이 정직해진다 (어긋나면 누수/거짓점수).
DATA_PATH = Path("data/action_data.csv")
SEED = 42                 # train_action.SEED
VAL_SPLIT = 0.2           # train_action: model.fit(validation_split=0.2)
LABELS = A.LABELS         # ["emergency", "dispatch", "guide", "none"]

# 이음새(seam) 점검용 고정 probe — guide 질문이 action 에서 guide 로 가는지,
# none 과 얼마나 헷갈리는지 본다. (chat_app 의 'guide 질문이 none 으로 새던' 버그의 계측)
SEAM_GUIDE_PROBES = [
    "모기 어떻게 없애요?",
    "러브버그 예방법 알려줘",
    "진드기 물리지 않으려면 어떻게 해요?",
    "바퀴벌레 왜 생겨요?",
    "빈대 퇴치 방법이 뭔가요?",
    "말벌 안 생기게 하려면 어떻게 하나요?",
    "모기 기피제 어떤 게 좋아요?",
    "빈대 흔적은 어떻게 확인해요?",
]


def load_holdout():
    """train_action 의 split 을 재현해, 가중치가 본 적 없는 tail 20% 를 반환."""
    df = pd.read_csv(DATA_PATH).sample(frac=1, random_state=SEED).reset_index(drop=True)
    n = len(df)
    split_at = int(n * (1.0 - VAL_SPLIT))  # Keras: train=[:split_at], val=[split_at:]
    train, holdout = df.iloc[:split_at], df.iloc[split_at:]

    # 누수 게이트: 홀드아웃 문장이 train 에 단 1건도 없어야 한다.
    train_texts = set(train["text"].astype(str))
    leaked = sorted({t for t in holdout["text"].astype(str) if t in train_texts})
    assert not leaked, f"누수! train 과 겹치는 홀드아웃 문장 {len(leaked)}건: {leaked[:5]}"

    return train, holdout


def confusion_and_metrics(rows, predict_fn):
    """rows=[(text, gold)] → (정확도, 클래스별 P/R, 혼동행렬 dict[gold][pred])."""
    idx = {l: i for i, l in enumerate(LABELS)}
    cm = [[0] * len(LABELS) for _ in LABELS]  # cm[gold][pred]
    preds = []
    for text, gold in rows:
        pred = predict_fn(text)
        preds.append((text, gold, pred))
        if gold in idx and pred in idx:
            cm[idx[gold]][idx[pred]] += 1

    total = sum(sum(r) for r in cm)
    correct = sum(cm[i][i] for i in range(len(LABELS)))
    acc = correct / total if total else 0.0

    metrics = {}
    for i, l in enumerate(LABELS):
        tp = cm[i][i]
        fp = sum(cm[g][i] for g in range(len(LABELS))) - tp
        fn = sum(cm[i]) - tp
        support = sum(cm[i])
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        metrics[l] = {"P": prec, "R": rec, "F1": f1, "support": support}
    return acc, metrics, cm, preds


def print_confusion(cm):
    head = "gold\\pred ".ljust(11) + "".join(f"{l[:4]:>7}" for l in LABELS) + f"{'합':>7}"
    print(head)
    for i, l in enumerate(LABELS):
        row = f"{l:10}" + "".join(f"{cm[i][j]:>7}" for j in range(len(LABELS)))
        print(row + f"{sum(cm[i]):>7}")


def main():
    train, holdout = load_holdout()
    print(f"데이터 {len(train) + len(holdout)}행 → train {len(train)} / 홀드아웃 {len(holdout)} "
          f"(seed={SEED}, val_split={VAL_SPLIT}, 누수 0 검증 통과)\n")

    L = A.load_action()
    predict_fn = lambda t: A.predict_action(t, *L)["action"]  # noqa: E731

    rows = [(str(r["text"]), str(r["action"])) for _, r in holdout.iterrows()]
    acc, metrics, cm, _ = confusion_and_metrics(rows, predict_fn)

    print(f"=== 홀드아웃 정확도(accuracy): {acc * 100:.1f}%  ({sum(cm[i][i] for i in range(len(LABELS)))}/{len(rows)}) ===\n")

    print("클래스별 지표:")
    print(f"  {'action':10} {'precision':>10} {'recall':>9} {'f1':>7} {'n':>6}")
    for l in LABELS:
        m = metrics[l]
        print(f"  {l:10} {m['P'] * 100:9.1f}% {m['R'] * 100:8.1f}% {m['F1'] * 100:6.1f}% {m['support']:6}")
    macro_f1 = sum(metrics[l]["F1"] for l in LABELS) / len(LABELS)
    print(f"  {'(macro F1)':10} {'':>10} {'':>9} {macro_f1 * 100:6.1f}%\n")

    print("혼동행렬 (행=정답 gold, 열=예측 pred):")
    print_confusion(cm)

    # ── 이음새 점검: guide 질문 → action ───────────────────────────
    print("\n=== 이음새(seam) 점검: guide 질문이 guide 로 가는가 (none 으로 새는가) ===")
    seam_rows = [(t, "guide") for t in SEAM_GUIDE_PROBES]
    seam_acc, _, seam_cm, seam_preds = confusion_and_metrics(seam_rows, predict_fn)
    print(f"  {'pred':10} {'문장'}")
    leak_to_none = 0
    for t, _, pred in seam_preds:
        mark = "O" if pred == "guide" else ("→none!" if pred == "none" else f"→{pred}")
        if pred == "none":
            leak_to_none += 1
        print(f"  {mark:10} {t}")
    print(f"\n  guide 적중: {sum(1 for _, _, p in seam_preds if p == 'guide')}/{len(seam_preds)}"
          f" = {seam_acc * 100:.0f}%   |   none 으로 샘: {leak_to_none}/{len(seam_preds)}")

    # 누수 게이트만 hard assert (정확도는 보고용 — 모델 완벽 가정 안 함).
    print("\n[GATE] 누수 0 assert 통과 ✅")


if __name__ == "__main__":
    main()
