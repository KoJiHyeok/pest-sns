"""해충 분류 추론 모듈.

train_to_tflite.py가 만든 3개 산출물(models/)을 읽어
한글 문장 → 해충 클래스 + 확률을 돌려준다.

핵심: .tflite 모델은 '숫자(토큰) → 확률'만 한다. 한글 문장을 숫자로 바꾸는
전처리는 여기서 학습 때와 '똑같이' 재현해야 한다(vocab.json으로 복원).
"""
import json
import re
import unicodedata
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
import tensorflow as tf  # noqa: E402
from kiwipiepy import Kiwi  # noqa: E402

MODEL_DIR = Path(__file__).parent / "models"
SEQ_LEN = 32
MAX_TOKENS = 2000

# 한국어 형태소 토큰화: "모기가" → "모기"(조사 '가' 제거)처럼 어근만 독립 토큰으로 만든다.
# 평균 풀링(GlobalAveragePooling)이 모든 토큰을 평균내므로, 조사·어미 같은 기능어를 남기면
# 핵심어(해충명) 신호가 희석된다 → 내용어(명사·동사·형용사·부사)만 남겨 신호를 집중시킨다.
# 학습(train_to_tflite.py)과 추론이 '똑같은' 토큰화를 써야 하므로 여기 단일 정의를 공유한다.
_kiwi = None
# 남길 품사 prefix: 명사(NN*/NR/NP) · 동사/형용사(VV/VA/VX, 단 copula VC*는 제외) · 부사(MA*) · 외국어/숫자/어근
_KEEP_TAGS = ("NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "VX", "MAG", "MAJ", "SL", "SH", "SN", "XR")
_PRED_TERM_TAIL = r"(?=$|[\s.,!?~…]|[이가은는을를도과와에의만부터까지한테에게랑이며입니다인데으로로집])"
_NORMALIZE_RULES = (
    # 사용자가 띄어 쓰거나 영어로 입력한 해충명을 학습 vocab에 있는 표기로 맞춘다.
    (re.compile(r"(?i)\blove\s*[-_ ]?\s*bugs?(?=$|[^A-Za-z])"), "러브버그"),
    (re.compile(r"러브\s*[-_ ]?\s*버그" + _PRED_TERM_TAIL), "러브버그"),
    (re.compile(r"말\s+벌" + _PRED_TERM_TAIL), "말벌"),
    (re.compile(r"바퀴\s*벌레" + _PRED_TERM_TAIL), "바퀴벌레"),
    (re.compile(r"진\s*드기" + _PRED_TERM_TAIL), "진드기"),
    (re.compile(r"빈\s*대" + _PRED_TERM_TAIL), "빈대"),
)
_PEST_TOKEN_TO_LABEL = {
    "모기": "mosquito",
    "바퀴벌레": "cockroach",
    "러브_버그": "lovebug",
    "말벌": "wasp",
    "빈대": "bedbug",
    "진드기": "tick",
}
_REPORT_CONTEXT_TOKENS = {
    "많", "발견", "출현", "불편", "떼", "집", "무섭", "조심", "들어오",
    "붙", "물리", "가렵", "빨갛", "붓", "기어다니", "나오", "보", "생기",
    "신고", "때문", "못", "널", "윙윙거리", "살충제", "뿌리",
}
_NON_REPORT_CONTEXT_TOKENS = {
    "뉴스", "영화", "노래", "소문", "검색", "사진", "기사", "관련", "책",
    "다큐멘터리", "게임", "캐릭터", "키", "링", "선물", "밈", "금리",
    "대출", "제목", "모양", "읽", "듣", "보내",
}
_LEXICAL_CONFIDENCE_FLOOR = 0.85


def normalize_text(text):
    """사용자 입력 표기 변형을 모델 학습 표기로 정규화한다."""
    normalized = unicodedata.normalize("NFKC", str(text))
    for pattern, replacement in _NORMALIZE_RULES:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def calibrate_probs(tokenized_text, probs, label_map):
    """명확한 해충명+제보 문맥은 작은 모델의 확신도를 보정한다.

    작은 평균풀링 모델은 토큰이 몇 개만 추가돼도 확률이 80% 근처로 눌릴 수 있다.
    단순 키워드 매칭만으로 none 문맥을 망치지 않도록, 비제보 문맥 토큰이 있으면 보정하지 않는다.
    """
    tokens = set(tokenized_text.split())
    if not tokens or tokens & _NON_REPORT_CONTEXT_TOKENS or not (tokens & _REPORT_CONTEXT_TOKENS):
        return probs

    labels = {label for token, label in _PEST_TOKEN_TO_LABEL.items() if token in tokens}
    if len(labels) != 1:
        return probs

    label_to_idx = {label: int(idx) for idx, label in label_map.items()}
    target_label = next(iter(labels))
    target_idx = label_to_idx.get(target_label)
    if target_idx is None or int(np.argmax(probs)) != target_idx:
        return probs
    if float(probs[target_idx]) >= _LEXICAL_CONFIDENCE_FLOOR:
        return probs

    calibrated = probs.astype("float32", copy=True)
    other_sum = float(np.sum(calibrated) - calibrated[target_idx])
    if other_sum > 0:
        scale = (1.0 - _LEXICAL_CONFIDENCE_FLOOR) / other_sum
        for i in range(len(calibrated)):
            if i != target_idx:
                calibrated[i] *= scale
    else:
        calibrated.fill((1.0 - _LEXICAL_CONFIDENCE_FLOOR) / (len(calibrated) - 1))
    calibrated[target_idx] = _LEXICAL_CONFIDENCE_FLOOR
    return calibrated


def tokenize(text):
    """한국어 문장 → 내용어 형태소를 공백으로 이은 문자열 (학습·추론 공통 전처리).

    예) "모기가 서울숲에 너무 많아요" → "모기 서울숲 너무 많"
    form 내부 공백('러브 버그')은 '_'로 치환해 한 토큰으로 유지한다(공백 분리로 쪼개지지 않게).
    """
    global _kiwi
    if _kiwi is None:
        _kiwi = Kiwi()
    text = normalize_text(text)
    return " ".join(
        tok.form.replace(" ", "_")
        for tok in _kiwi.tokenize(text)
        if tok.tag.startswith(_KEEP_TAGS)
    )

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
    # standardize=None: 토큰화는 kiwi(tokenize)가 이미 했으므로 공백 분리만 한다.
    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=MAX_TOKENS,
        output_mode="int",
        output_sequence_length=SEQ_LEN,
        standardize=None,
        split="whitespace",
    )
    vectorizer.set_vocabulary(vocab[2:])

    interp = tf.lite.Interpreter(model_path=str(MODEL_DIR / "pest_text_model.tflite"))
    interp.allocate_tensors()
    return vectorizer, interp, label_map


def predict(text, vectorizer, interp, label_map):
    """문장 1개 → (영문라벨, 한글, 확률[클래스순], 라벨순서리스트)."""
    tokenized = tokenize(text)
    x = vectorizer([tokenized]).numpy().astype("int32")  # (1, 32)

    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]
    interp.set_tensor(inp["index"], x)
    interp.invoke()
    probs = interp.get_tensor(out["index"])[0]  # (클래스수,)
    probs = calibrate_probs(tokenized, probs, label_map)

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
