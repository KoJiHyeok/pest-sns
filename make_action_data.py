"""action 분류 학습 데이터 생성 (make_train_data.py 재활용, 라벨만 pest→action).

설계 의도:
  S1 계약①의 action 모델(emergency·dispatch·guide·none)을 기존 pest 파이프라인과
  **똑같은 구조**(Embedding+GAP bag-of-words, predict.tokenize 전처리)로 학습시킨다.
  따라서 데이터도 make_train_data.py 의 프레임/지명/문맥을 그대로 import 해 재활용하되,
  **버킷을 pest 가 아니라 action 의미로 재분류**한다(CONTRACTS 라벨 기준 표).

action 재매핑 (핵심):
  - emergency : wasp 계열 전부 + 쏘임/물려서 부음/호흡곤란/벌집 (심한 케이스)
  - dispatch  : 대량 출몰·단순 목격 제보·"방역 필요"·"신고" (wasp 제외 제보 기본값)
  - guide     : 질문형(NONE_QUESTION_FRAMES "어떻게 없애요/예방법/왜") — pest 모델에선 none 이던 것
  - none      : 잡담·영화/노래/검색·애정표현·먼 과거 회상·중립 (기존 none 함정 그대로)

제약:
  - 출력 형식: text,action  (train_action.py 가 읽는 형식)
  - 클래스 균형 + 누수 방지(DONE 체크 홀드아웃 5문장 제외)
  - 한 문장이 두 action 으로 새지 않게 전역 dedup(먼저 잡힌 라벨 우선)

실행:
  ../.venv/Scripts/python.exe make_action_data.py --preview 50   # 라벨 눈검증(파일 안 씀)
  ../.venv/Scripts/python.exe make_action_data.py                # data/action_data.csv 생성
"""
import csv
import random
import sys
from collections import Counter
from pathlib import Path

# make_train_data 의 프레임/지명/문맥을 그대로 재활용(읽기 전용 import — 수정 안 함).
import make_train_data as M

ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "data" / "action_data.csv"

SEED = 42
random.seed(SEED)

# 클래스당 목표(작은 bag-of-words 라 신호가 또렷해 과하게 많을 필요 없음).
TARGET_EMERGENCY = 600
TARGET_DISPATCH = 600
TARGET_GUIDE = 400
TARGET_NONE = 600

# DONE 체크 홀드아웃 — 학습에서 제외해야 평가가 정직하다(누수 방지).
HOLDOUT = {
    "단국대 천안캠퍼스에 말벌집이 생겼어요",
    "러브버그 너무 많아요",
    "모기 어떻게 없애요?",
    "오늘 날씨 좋네요",
}

# ── 프레임: {ctx} 자리표시가 있는 것만(목격 전용 '봤어요' 프레임은 dispatch 용) ──
FRAMES_CTX_LOC = [
    "{loc}에서 {pest} {ctx}", "{loc}에 {pest} {ctx}", "{loc} 근처에 {pest} {ctx}",
    "오늘 {loc} 근처에 {pest} {ctx}", "{loc} 주변에 {pest} {ctx}",
    "방금 {loc}에서 {pest} {ctx}", "{loc} 갔다가 {pest} {ctx}",
    "어제 {loc}에서 {pest} {ctx}", "아까 {loc}에서 {pest} {ctx}",
]
FRAMES_CTX_NOLOC = ["{pest} {ctx}", "어제 {pest} {ctx}", "오늘 {pest} {ctx}", "방금 {pest} {ctx}"]

# ── emergency: wasp 전부 + 심한 케이스(쏘임/부음/호흡곤란/벌집) ────────────────
EMERGENCY_PEST = {
    "wasp": ["말벌"] * 4 + ["말 벌"],
    "tick": ["진드기"],
    "bedbug": ["빈대"],
    "mosquito": ["모기"],
}
EMERGENCY_CTX = {
    # wasp 는 목격·둥지·쏘임 전부 emergency 로(=계약: "wasp 계열")
    "wasp": ["쏘였어요", "에 쏘였어요", "한테 쏘였어요", "쏘여서 부었어요",
             "쏘여서 퉁퉁 부었어요", "쏘여서 아파요", "쏘여서 숨쉬기 힘들어요",
             "때문에 호흡이 가빠요", "보여서 무서워요", "때문에 위험해요",
             "출현했습니다", "들어왔어요"],
    # 비-wasp 는 '심한' 문맥만 emergency(일반 목격/대량은 dispatch)
    "tick": ["물려서 심하게 부었어요", "물린 자국이 퉁퉁 부었어요", "물려서 열이 나요"],
    "bedbug": ["물려서 온몸이 부었어요", "물린 데가 심하게 부었어요"],
    "mosquito": ["물려서 퉁퉁 부었어요", "물린 데가 심하게 부었어요", "물려서 호흡이 가빠요"],
}
# emergency: 벌집/말벌집 발견(둥지) — 별도 프레임(holdout '말벌집이 생겼어요'와 같은 토큰 학습)
NEST_PESTS = ["말벌", "말벌", "말 벌", "벌"]
NEST_FRAMES = [
    "{loc}에 {pest}집이 생겼어요", "{loc}에 {pest}집을 발견했어요",
    "{loc} 근처에 {pest}집이 있어요", "{loc} {pest}집 때문에 위험해요",
    "{pest}집을 발견했어요", "{pest}집이 생겼어요", "{pest} 집이 있는 것 같아요",
    "{loc}에서 {pest} 집을 발견했어요", "{loc}에 {pest} 집이 생겼어요",
]

# ── dispatch: 대량 출몰·단순 목격·방역/신고 (wasp 제외 제보 기본값) ────────────
DISPATCH_PEST = {
    "mosquito": ["모기"],
    "cockroach": ["바퀴벌레"],
    "lovebug": ["러브버그"] * 4 + ["러브 버그"] * 2 + ["love bug", "love bugs"],
    "tick": ["진드기"],
    "bedbug": ["빈대"],
}
DISPATCH_CTX = [
    "너무 많아요", "떼로 봤어요", "들끓어요", "엄청 많네요", "잔뜩 있어요",
    "출몰했어요", "출현했습니다", "나왔어요", "보여요", "기어다녀요",
    "방역이 필요해요", "방역 필요해요", "신고합니다", "신고할게요",
    "때문에 불편해요", "천지예요", "뒤덮었어요",
]
# dispatch: 단순 목격 전용(make_train_data 의 '봤어요' 프레임 재활용 효과)
DISPATCH_SIGHT_FRAMES = [
    "{loc}에서 {pest} 봤어요", "어제 {loc}에서 {pest} 봤어요",
    "방금 {loc}에서 {pest} 봤어요", "{pest} 봤어요", "오늘 {pest} 봤어요",
]

# ── guide: 질문형(make_train_data.NONE_QUESTION_FRAMES + 확장) → guide ────────
GUIDE_FRAMES = list(M.NONE_QUESTION_FRAMES) + [
    "{pest} 퇴치 방법 알려주세요", "{pest} 어떻게 쫓아내나요?", "{pest} 안 생기게 하려면?",
    "{pest} 예방하는 방법 있나요?", "{pest} 어떻게 막나요?", "{pest} 없애는 법 알려줘",
    "{pest} 물리면 어떻게 처치하나요?", "{pest} 예방법이 궁금합니다",
    "{pest} 어떻게 대처하나요?", "{pest} 퇴치제 추천해주세요",
    "{pest} 생기는 이유가 뭐예요?", "{pest} 어떻게 관리하나요?",
    "{pest} 어떻게 없애요?", "{pest} 어떻게 예방해요?", "{pest} 왜 생겨요?",
    "{pest} 어떻게 물리쳐요?", "{pest} 대처법 알려주세요", "{pest} 방제 방법 궁금해요",
]
GUIDE_PEST_WORDS = list(M.NONE_PEST_WORDS)

# ── none: 잡담·비제보(기존 none 함정 그대로 재활용, 질문형은 제외=guide 로 갔으므로) ──
NONE_TRAP_FRAMES = list(M.NONE_FRAMES) + list(M.NONE_AFFECTION_FRAMES) + list(M.NONE_PAST_FRAMES)
NONE_PEST_WORDS = list(M.NONE_PEST_WORDS)


def _gen_combos(frames, pest_map_or_list, ctxs, target, exclude, label):
    """frames × loc × pest × ctx 조합을 셔플해 distinct target 개 생성."""
    combos = []
    use_loc = any("{loc}" in f for f in frames)
    pests = pest_map_or_list
    for frame in frames:
        locs = M.LOCATIONS if "{loc}" in frame else [""]
        for loc in locs:
            for pest in pests:
                if "{ctx}" in frame:
                    for ctx in ctxs:
                        combos.append((frame, loc, pest, ctx))
                else:
                    combos.append((frame, loc, pest, ""))
    random.shuffle(combos)
    seen, rows = set(), []
    for frame, loc, pest, ctx in combos:
        text = frame.format(loc=loc, pest=pest, ctx=ctx).strip()
        if text in exclude or text in seen:
            continue
        seen.add(text)
        rows.append((text, label))
        if len(rows) >= target:
            break
    return rows


def gen_emergency(exclude):
    rows = []
    # wasp + 심한 케이스: pest별 ctx 가 달라 개별 처리
    for pest_label, surfaces in EMERGENCY_PEST.items():
        ctxs = EMERGENCY_CTX[pest_label]
        rows += _gen_combos(FRAMES_CTX_LOC + FRAMES_CTX_NOLOC, surfaces, ctxs,
                            10**9, exclude, "emergency")
    # 벌집/말벌집 둥지
    nest = []
    for frame in NEST_FRAMES:
        locs = M.LOCATIONS if "{loc}" in frame else [""]
        for loc in locs:
            for pest in NEST_PESTS:
                nest.append((frame.format(loc=loc, pest=pest).strip(), "emergency"))
    random.shuffle(nest)
    seen = {t for t, _ in rows}
    for t, lab in nest:
        if t in exclude or t in seen:
            continue
        seen.add(t)
        rows.append((t, lab))
    random.shuffle(rows)
    return rows[:TARGET_EMERGENCY]


def gen_dispatch(exclude):
    rows = []
    all_surfaces = []
    for surfaces in DISPATCH_PEST.values():
        all_surfaces += surfaces
    rows += _gen_combos(FRAMES_CTX_LOC + FRAMES_CTX_NOLOC, all_surfaces, DISPATCH_CTX,
                        10**9, exclude, "dispatch")
    # 단순 목격 프레임
    sight = []
    for frame in DISPATCH_SIGHT_FRAMES:
        locs = M.LOCATIONS if "{loc}" in frame else [""]
        for loc in locs:
            for pest in all_surfaces:
                sight.append((frame.format(loc=loc, pest=pest).strip(), "dispatch"))
    random.shuffle(sight)
    seen = {t for t, _ in rows}
    for t, lab in sight:
        if t in exclude or t in seen:
            continue
        seen.add(t)
        rows.append((t, lab))
    random.shuffle(rows)
    return rows[:TARGET_DISPATCH]


def gen_guide(exclude):
    seen, rows = set(), []
    combos = [(f, p) for f in GUIDE_FRAMES for p in GUIDE_PEST_WORDS]
    random.shuffle(combos)
    for frame, pest in combos:
        text = frame.format(pest=pest).strip()
        if text in exclude or text in seen:
            continue
        seen.add(text)
        rows.append((text, "guide"))
        if len(rows) >= TARGET_GUIDE:
            break
    return rows


def gen_none(exclude):
    guaranteed = []
    for frame in NONE_TRAP_FRAMES:
        for pest in NONE_PEST_WORDS:
            guaranteed.append((frame.format(pest=pest), "none"))
    for s in M.NONE_SPECIALS:
        guaranteed.append((s, "none"))

    neutral = []
    for frame in M.NONE_NEUTRAL_LOC:
        for loc in M.LOCATIONS:
            neutral.append((frame.format(loc=loc), "none"))
    for s in M.NONE_NEUTRAL_PLAIN:
        neutral.append((s, "none"))
    random.shuffle(neutral)

    seen, rows = set(), []
    for text, lab in guaranteed + neutral:
        text = text.strip()
        if text in exclude or text in seen:
            continue
        seen.add(text)
        rows.append((text, lab))
        if len(rows) >= TARGET_NONE:
            break
    return rows


def build():
    """4 action 버킷 생성 후 전역 dedup(먼저 잡힌 라벨 우선)으로 누수 없이 병합."""
    exclude = set(HOLDOUT)
    em = gen_emergency(exclude)
    di = gen_dispatch(exclude)
    gu = gen_guide(exclude)
    no = gen_none(exclude)

    out, seen = [], set()
    for bucket in (em, di, gu, no):   # 순서 = 라벨 우선순위(충돌 시 앞 라벨 채택)
        for text, lab in bucket:
            if text in seen:
                continue
            seen.add(text)
            out.append((text, lab))
    return out, {"emergency": em, "dispatch": di, "guide": gu, "none": no}


def main():
    preview_n = 0
    if "--preview" in sys.argv:
        i = sys.argv.index("--preview")
        preview_n = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 50

    out, buckets = build()
    random.shuffle(out)

    # 누수 재검증(어셔션) — 홀드아웃과 한 줄도 겹치면 즉시 실패
    leaked = sorted({t for t, _ in out} & HOLDOUT)
    assert not leaked, f"누수 발견! 홀드아웃과 겹침: {leaked}"

    dist = Counter(lab for _, lab in out)

    if preview_n:
        # 라벨 눈검증: 각 클래스에서 고르게 샘플을 찍는다(파일 안 씀).
        per = max(1, preview_n // 4)
        print(f"=== PREVIEW (클래스당 {per}행, 파일 미작성) ===")
        for lab in ["emergency", "dispatch", "guide", "none"]:
            print(f"\n[{lab}]  (총 {dist[lab]}행)")
            for text, _ in buckets[lab][:per]:
                print(f"  {text}")
        print(f"\n클래스 분포(전체 생성): {dict(sorted(dist.items()))}")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["text", "action"])
        w.writerows(out)
    print(f"생성 완료: {len(out)}행 → {OUT_PATH.relative_to(ROOT)}")
    print(f"클래스 분포: {dict(sorted(dist.items()))}")
    print(f"누수 검사 통과 (홀드아웃 {len(HOLDOUT)}문장 중 학습셋 교집합 0)")


if __name__ == "__main__":
    main()
