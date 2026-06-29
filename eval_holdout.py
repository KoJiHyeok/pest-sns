"""고정된 held-out 테스트셋으로 모델을 '정직하게' 평가한다.

test_sentences.csv 의 문장은 학습 데이터(sample_pest_sns.csv)에 없는 새 표현이어야 한다.
아래에서 두 셋의 교집합을 검사해 누수(leakage)를 막는다 — 겹치면 점수가 부풀려지기 때문.
실행:  ../.venv/Scripts/python.exe eval_holdout.py
"""
import warnings

warnings.filterwarnings("ignore")
import pandas as pd  # noqa: E402

import predict as P  # noqa: E402

TARGET = "모기가 서울숲에 너무 많아요"
MIN_CONFIDENCE = 0.8
REGRESSION_CASES = (
    ("love bug가 너무 많아요", "lovebug"),
    ("love bugs가 창문에 붙었어요", "lovebug"),
    ("LOVE BUG 때문에 빨래를 못 널겠어요", "lovebug"),
    ("I love bug", "none"),
    ("I love bugs", "none"),
    ("love bug 노래를 들었어요", "none"),
    ("love bug라는 표현을 배웠어요", "none"),
)


def main():
    train_texts = set(pd.read_csv("sample_pest_sns.csv")["text"].astype(str))
    test = pd.read_csv("test_sentences.csv")

    leaked = [t for t in test["text"].astype(str) if t in train_texts]
    assert not leaked, f"누수! 학습셋과 겹치는 테스트 문장: {leaked}"

    vec, interp, lm = P.load()
    ok = 0
    confident = 0
    print(f"{'':2} {'예측':10} {'확신도':>5}  문장 (기대)")
    for _, row in test.iterrows():
        t, exp = str(row["text"]), str(row["pest_label"])
        en, _, probs, _ = P.predict(t, vec, interp, lm)
        hit = en == exp
        is_confident = max(probs) >= MIN_CONFIDENCE
        ok += hit
        confident += is_confident
        mark = "O" if hit and is_confident else "X"
        print(f"{mark:2} {en:10} {max(probs) * 100:4.0f}%  {t}  (기대={exp})")

    print(f"\nhold-out 정확도: {ok}/{len(test)} = {ok / len(test) * 100:.0f}%")
    print(f"80% 이상 확신도: {confident}/{len(test)} = {confident / len(test) * 100:.0f}%")

    en, _, probs, _ = P.predict(TARGET, vec, interp, lm)
    c = max(probs)
    verdict = "PASS" if en == "mosquito" and c > 0.8 else "FAIL"
    print(f"[TARGET] {TARGET} -> {en} ({c * 100:.0f}%)  {verdict}")

    regression_ok = 0
    print("\n영어 love bug 회귀:")
    for t, exp in REGRESSION_CASES:
        en, _, probs, _ = P.predict(t, vec, interp, lm)
        c = max(probs)
        hit = en == exp and c >= MIN_CONFIDENCE
        regression_ok += hit
        mark = "O" if hit else "X"
        print(f"{mark:2} {en:10} {c * 100:4.0f}%  {t}  (기대={exp})")

    assert ok == len(test), "정답이 아닌 hold-out 문장이 있습니다."
    assert confident == len(test), f"{MIN_CONFIDENCE * 100:.0f}% 미만 확신도 문장이 있습니다."
    assert regression_ok == len(REGRESSION_CASES), "영어 love bug 회귀 케이스가 실패했습니다."


if __name__ == "__main__":
    main()
