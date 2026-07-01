"""해충 분류 학습 데이터 대량 생성 (sample_pest_sns.csv 확장).

설계 의도 (이 모델 구조에 맞춤):
  모델은 Embedding + GlobalAveragePooling 의 '가벼운 bag-of-words' 다.
  kiwi 토큰화가 조사·어미를 떼므로(predict.tokenize), 모델이 실제로 학습하는 건
  **내용어(해충명 · 제보 문맥어 vs 비제보 문맥어 · 지명)의 조합**이다.
  따라서 다양성은 (1) 지명 (2) 제보 문맥 동사/표현 (3) none 의 '함정'(해충명이
  비제보 문맥에 등장) 에 집중한다 — 문장 부호·어미 변형은 어차피 토큰화로 사라진다.

제약 (반드시 준수):
  - 출력 형식: text,pest_label,location,is_real  (train_to_tflite.py 가 읽는 형식)
  - eval_holdout.py 는 학습셋이 test_sentences.csv·회귀셋과 **한 줄도 겹치면 안 된다**고
    assert 한다 → 생성 결과에서 그 문장들을 제거(누수 방지).
  - 원본 시드(sample_pest_sns_seed175.csv, 손으로 만든 까다로운 케이스)는 보존·병합한다.

실행:  ../.venv/Scripts/python.exe make_train_data.py
출력:  sample_pest_sns.csv  (원본 175행 + 생성분, 중복·누수 제거, 클래스 균형)
"""
import csv
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "sample_pest_sns_seed175.csv"   # 손으로 만든 원본 (병합 시드)
OUT_PATH = ROOT / "sample_pest_sns.csv"            # 학습 스크립트가 읽는 파일
TEST_PATH = ROOT / "test_sentences.csv"            # 누수 방지용 제외 목록

SEED = 42
TARGET_PEST = 700    # 해충 클래스당 목표 행 수
TARGET_NONE = 1000   # none 목표 행 수 (함정 케이스 전부 포함 + 중립 채움)

random.seed(SEED)

# ── 지명 (제보 문맥에서 '중립'이 되도록 다양하게) ───────────────────────────
LOCATIONS = [
    "강남역", "홍대입구역", "잠실역", "여의도공원", "광화문", "서울숲", "신촌역",
    "건대입구역", "성수역", "이태원역", "노원역", "사당역", "천호역", "은평구 불광천",
    "뚝섬한강공원", "수원역", "안양역", "정자역", "일산 호수공원", "인천 송도",
    "부천역", "의정부역", "모란역", "광교호수공원", "동탄", "대전역", "천안아산역",
    "부산 해운대", "부산 광안리", "대구 동성로", "광주 충장로", "제주 노형동",
    "춘천 명동", "전주 한옥마을", "포항 영일대", "창원 상남동", "울산 삼산동",
    "청주 성안길", "두정역", "천안역", "불당동", "백석대", "단국대 천안캠퍼스",
    "한강공원", "올림픽공원", "북서울꿈의숲", "양재시민의숲", "남산공원",
    "보라매공원", "월드컵공원", "어린이대공원", "석촌호수", "경의선숲길",
]

# ── 해충별 표기 변형 (canonical 우세하게 가중) + 제보 문맥 표현 ──────────────
PEST_SURFACES = {
    "mosquito":  ["모기"],
    "cockroach": ["바퀴벌레"],
    "lovebug":   ["러브버그"] * 4 + ["러브 버그"] * 2 + ["love bug", "love bugs"],
    "wasp":      ["말벌"] * 4 + ["말 벌"],
    "tick":      ["진드기"],
    "bedbug":    ["빈대"],
}
PEST_CTX = {
    "mosquito":  ["너무 많아요", "떼로 봤어요", "물렸어요", "때문에 가려워요", "들끓어요",
                  "윙윙거려서 잠을 설쳤어요", "엄청 많네요", "물려서 부었어요",
                  "출몰했어요", "때문에 밤새 못 잤어요"],
    "cockroach": ["나왔어요", "기어다녀요", "봤어요", "출몰했어요", "때문에 살충제 뿌렸어요",
                  "나와서 소름 끼쳤어요", "보여요", "출현했습니다", "때문에 소름 돋았어요"],
    "lovebug":   ["엄청 많아요", "떼로 봤어요", "방역 필요해요", "창문에 붙었어요",
                  "얼굴에 붙어요", "때문에 빨래를 못 널겠어요", "뒤덮었어요", "들끓어요",
                  "천지예요"],
    "wasp":      ["보여서 무서워요", "집이 있는 것 같아요", "때문에 불편합니다",
                  "윙윙거려서 무서워요", "조심하세요", "출현했습니다", "집을 발견했어요",
                  "들어왔어요"],
    "tick":      ["조심하세요", "물렸어요", "너무 많아요", "떼로 봤어요",
                  "물린 자국이 부었어요", "많대요", "출몰했어요", "주의하세요"],
    "bedbug":    ["나왔어요", "물렸어요", "의심돼요", "발견했어요", "때문에 이불 삶았어요",
                  "나와서 잠 못 잤어요", "출몰했어요"],
}

# ── 제보 문장 프레임 (loc 있음/없음 혼합) ──────────────────────────────────
#   '어제·방금·오늘·아까' = 최근 과거 = 유효 제보. '봤어요'(목격)도 제보 신호로 충분히 학습시켜
#   '진드기 산에 많다는데' / '어제 말벌 봤어요' 가 none 으로 새지 않게 한다(먼 과거 none 의 균형추).
FRAMES_LOC = [
    "{loc}에서 {pest} {ctx}",
    "{loc}에 {pest} {ctx}",
    "{loc} 근처에 {pest} {ctx}",
    "오늘 {loc} 근처에 {pest} {ctx}",
    "{loc} 주변에 {pest} {ctx}",
    "방금 {loc}에서 {pest} {ctx}",
    "{loc} 갔다가 {pest} {ctx}",
    "어제 {loc}에서 {pest} {ctx}",
    "아까 {loc}에서 {pest} {ctx}",
    "{loc}에서 {pest} 봤어요",
    "어제 {loc}에서 {pest} 봤어요",
    "방금 {loc}에서 {pest} 봤어요",
]
FRAMES_NOLOC = [
    "{pest} {ctx}",
    "어제 {pest} {ctx}",
    "오늘 {pest} {ctx}",
    "{pest} 봤어요",
    "어제 {pest} 봤어요",
    "오늘 {pest} 봤어요",
    "방금 {pest} 봤어요",
    "{pest} 많다는데",
    "{pest} 너무 많다는데",
]

# ── none: 함정 (해충명이 '비제보' 문맥에 등장 → 반드시 none) ─────────────────
NONE_PEST_WORDS = ["모기", "바퀴벌레", "러브버그", "러브 버그", "말벌", "말 벌",
                   "진드기", "빈대", "love bug"]
NONE_FRAMES = [
    "{pest} 영화 제목 같네요",
    "{pest} 뉴스 봤는데 신기하네요",
    "{pest} 검색해보니 사진이 징그러워요",
    "{pest} 소문만 들었습니다",
    "{pest} 관련 기사 읽었습니다",
    "{pest} 다큐멘터리 봤어요",
    "{pest} 게임 캐릭터가 귀엽다",
    "{pest} 밈 친구가 보냈어요",
    "{pest} 모양 키링을 샀어요",
    "{pest} 책을 읽고 있어요",
    "{pest} 그림을 그렸어요",
    "{pest}라는 단어를 배웠어요",
    "{pest} 사진을 봤어요",
    "{pest} 캐릭터 인형을 샀어요",
]
# none: 애정/긍정 함정 (해충명 + '사랑해·귀여워·좋아해' → 제보가 아님)
#   "난 러브 버그를 사랑해" 같은 문장은 해충 출몰 신고가 아니라 애정 표현이다.
#   감정어 토큰(사랑·귀엽·좋아하·예쁘…)을 none 으로 학습시켜 제보 문맥과 분리한다.
NONE_AFFECTION_FRAMES = [
    "{pest} 너무 좋아", "{pest} 너무 좋아요", "난 {pest} 사랑해",
    "나는 {pest}를 사랑해", "{pest} 정말 사랑스러워", "{pest} 귀여워",
    "{pest} 너무 귀여워요", "{pest} 좋아해", "{pest} 응원해",
    "{pest} 캐릭터 좋아해", "{pest} 진짜 예뻐", "{pest} 키우고 싶어",
    "{pest} 팬이에요", "{pest} 보고 싶어",
]
# none: 질문/정보성 함정 (해충명 + '어디·어떻게·왜·알려줘' → 제보가 아니라 문의)
#   "말벌은 어디서 서식하나요?" 는 출몰 신고가 아니라 정보 질문이다.
#   질문어 토큰(어디·어떻·왜·궁금·알리·서식·특징·퇴치…)을 none 으로 학습시킨다.
NONE_QUESTION_FRAMES = [
    "{pest} 어디서 서식하나요?", "{pest} 어디서 사나요?", "{pest} 어떻게 없애나요?",
    "{pest} 어떻게 예방하나요?", "{pest} 왜 생기나요?", "{pest} 어떻게 생겼나요?",
    "{pest} 물리면 어떻게 하나요?", "{pest}에 대해 알려줘", "{pest} 정보 좀 알려주세요",
    "{pest} 특징이 뭐예요?", "{pest} 무엇을 먹나요?", "{pest} 언제 많이 나오나요?",
    "{pest} 퇴치 방법 궁금해요", "{pest}랑 비슷한 곤충이 뭐예요?",
]
# none: 먼 과거/회상 함정 (해충명 + '작년·예전·옛날' → 지금 출몰 신고가 아님)
#   "작년엔 말벌 많았는데" 는 회상이지 현재 제보가 아니다.
#   ⚠ '어제·오늘·방금' 같은 최근 과거는 유효 제보이므로 절대 넣지 않는다(제보 recall 보호).
#   먼 과거 표지 토큰(작년·예전·옛날·지난해·어리·그때·재작년·학창시절)만 none 으로 학습.
NONE_PAST_FRAMES = [
    "작년엔 {pest} 많았는데", "예전에 {pest} 진짜 많았어", "옛날엔 {pest} 자주 봤지",
    "어릴 때 {pest} 물린 적 있어", "지난해엔 {pest} 심했었지", "그땐 {pest} 많았는데",
    "재작년에 {pest} 본 적 있어", "학창시절엔 {pest} 흔했지",
    "예전엔 {pest} 많이 나왔었어", "옛날에 {pest} 때문에 고생했었지",
]
# none: 특수 함정 (관용구·동음이의·차량 바퀴 벌레 등) — 전부 포함
NONE_SPECIALS = [
    "빈대떡 먹고 싶다", "빈대떡이 맛있어요", "빈대떡 부쳐 먹었어요",
    "모기지 대출 금리 뉴스 봤어요", "주택담보 대출 받았어요",
    "러브라는 노래를 들었습니다", "사랑 노래를 들었어요",
    "자동차 앞바퀴에 벌레가 꼈어요", "뒷바퀴에 벌레가 끼었어요",
    "자전거 바퀴에 벌레가 묻었어요", "차 바퀴에 벌레가 끼었어요",
    "빈대 붙지 말라는 말을 들었어요",
]
# none: 순수 중립 (지명 기반) — 지명이 해충과 상관없음을 학습
NONE_NEUTRAL_LOC = [
    "{loc}에서 점심 먹었어요", "{loc} 산책 좋네요", "{loc} 날씨 맑아요",
    "{loc} 카페에서 공부 중이에요", "{loc} 사람 많네요", "{loc} 도착했습니다",
    "{loc}에서 친구 만났어요", "{loc} 다녀왔어요", "{loc}에서 커피 마셨어요",
    "{loc} 구경 잘했어요", "{loc} 야경 예쁘네요", "{loc}에서 쇼핑했어요",
    "{loc} 맛집 다녀왔어요", "{loc} 벚꽃 폈어요", "{loc}에서 자전거 탔어요",
    "{loc} 단풍 구경했어요",
]
# none: 순수 중립 (지명 없음)
NONE_NEUTRAL_PLAIN = [
    "오늘 날씨가 좋네요", "회사 회의가 길었어요", "운동을 좀 했어요",
    "새 신발이 마음에 들어요", "김밥을 먹었어요", "우산을 챙겼어요",
    "책상 정리를 했어요", "강아지랑 산책했어요", "주말에 영화 봤어요",
    "커피 한 잔 했어요", "벌써 여름이네요", "집에서 푹 쉬었어요",
    "오늘 야근했어요", "점심 뭐 먹지 고민돼요", "버스를 놓쳤어요",
    "넷플릭스 정주행했어요", "장보러 마트 갔어요", "친구랑 수다 떨었어요",
    "택배가 도착했어요", "낮잠을 잤어요",
]


def load_exclude():
    """누수 방지: 학습에서 빼야 하는 평가/회귀 문장 집합."""
    exclude = set()
    with TEST_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            exclude.add(row["text"].strip())
    # eval_holdout.py REGRESSION_CASES (코드와 동기화 — 바뀌면 같이 갱신)
    exclude.update([
        "love bug가 너무 많아요", "love bugs가 창문에 붙었어요",
        "LOVE BUG 때문에 빨래를 못 널겠어요", "I love bug", "I love bugs",
        "love bug 노래를 들었어요", "love bug라는 표현을 배웠어요",
    ])
    return exclude


def loc_of(text, frame):
    """프레임에 {loc} 가 있었으면 그 지명을, 없으면 '' 를 돌려준다(메타 컬럼용)."""
    return text if "{loc}" in frame else ""


def gen_pest(label, target, exclude):
    """한 해충 클래스의 (text, label, location) 후보를 target 개까지 distinct 생성."""
    surfaces, ctxs = PEST_SURFACES[label], PEST_CTX[label]
    combos = []
    for frame in FRAMES_LOC:
        for loc in LOCATIONS:
            for pest in surfaces:
                for ctx in ctxs:
                    combos.append((frame, loc, pest, ctx))
    for frame in FRAMES_NOLOC:
        for pest in surfaces:
            for ctx in ctxs:
                combos.append((frame, "", pest, ctx))
    random.shuffle(combos)

    seen, rows = set(), []
    for frame, loc, pest, ctx in combos:
        text = frame.format(loc=loc, pest=pest, ctx=ctx).strip()
        if text in exclude or text in seen:
            continue
        seen.add(text)
        rows.append((text, label, loc if "{loc}" in frame else ""))
        if len(rows) >= target:
            break
    return rows


def gen_none(target, exclude):
    """none: 함정(전부) + 특수(전부) 먼저 보장, 나머지는 중립으로 채운다."""
    guaranteed = []
    for frame in (NONE_FRAMES + NONE_AFFECTION_FRAMES + NONE_QUESTION_FRAMES
                  + NONE_PAST_FRAMES):
        for pest in NONE_PEST_WORDS:
            guaranteed.append((frame.format(pest=pest), "none", ""))
    for s in NONE_SPECIALS:
        guaranteed.append((s, "none", ""))

    neutral = []
    for frame in NONE_NEUTRAL_LOC:
        for loc in LOCATIONS:
            neutral.append((frame.format(loc=loc), "none", loc))
    for s in NONE_NEUTRAL_PLAIN:
        neutral.append((s, "none", ""))
    random.shuffle(neutral)

    seen, rows = set(), []
    for text, label, loc in guaranteed + neutral:
        text = text.strip()
        if text in exclude or text in seen:
            continue
        seen.add(text)
        rows.append((text, label, loc))
        if len(rows) >= target:
            break
    return rows


def load_seed():
    """손으로 만든 원본을 (text, label, location, is_real) 로 읽는다."""
    rows = []
    with SEED_PATH.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append((r["text"].strip(), r["pest_label"].strip(),
                         (r.get("location") or "").strip(),
                         (r.get("is_real") or "").strip()))
    return rows


def main():
    exclude = load_exclude()

    # 1) 시드(원본) 먼저 — 중복 병합 시 원본 라벨이 우선.
    #    원본에도 회귀 케이스("love bug 노래를 들었어요")가 1건 섞여 있어 제외 목록으로 거른다
    #    (eval 은 test_sentences 만 검사하지만, 회귀셋까지 빼야 평가가 완전히 정직해진다).
    out, seen = [], set()
    for text, label, loc, is_real in load_seed():
        if text in seen or text in exclude:
            continue
        seen.add(text)
        out.append((text, label, loc, is_real or ("0" if label == "none" else "1")))

    # 2) 생성분 병합
    generated = []
    for label in ["mosquito", "cockroach", "lovebug", "wasp", "tick", "bedbug"]:
        generated += gen_pest(label, TARGET_PEST, exclude)
    generated += gen_none(TARGET_NONE, exclude)

    for text, label, loc in generated:
        if text in seen:
            continue
        seen.add(text)
        out.append((text, label, loc, "0" if label == "none" else "1"))

    random.shuffle(out)

    # 3) 누수 재검증 (eval_holdout 의 assert 를 미리 흉내) — 겹치면 즉시 실패
    leaked = sorted({t for t, *_ in out} & exclude)
    assert not leaked, f"누수 발견! 평가셋과 겹침: {leaked[:5]}"

    # 4) 기록
    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["text", "pest_label", "location", "is_real"])
        w.writerows(out)

    dist = Counter(label for _, label, *_ in out)
    print(f"생성 완료: {len(out)}행 → {OUT_PATH.name}")
    print(f"클래스 분포: {dict(sorted(dist.items()))}")
    print(f"누수 검사 통과 (평가/회귀 {len(exclude)}문장 중 학습셋 교집합 0)")


if __name__ == "__main__":
    main()
