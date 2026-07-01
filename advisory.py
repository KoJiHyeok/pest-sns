# -*- coding: utf-8 -*-
"""이음새(seam) 보정 — pest 분류 ↔ action 분류 사이의 약점을 메우는 단일 출처.

8600 분석앱(`web/server.py`)과 8700 챗(`chat_app.py`)이 **같은 보정 규칙**을 쓰도록
한 곳에 모은다. 예전엔 두 파일에 같은 규칙이 복붙돼 있어, 한쪽만 고치면 조용히 갈라졌다.

작은 모델 두 개를 이어 붙이면 생기는 두 누수를 보정한다(서로 대칭):

  ① pest 모델은 none 인데 action 모델은 해충 action(≠none)으로 봤고, 원문에 해충 표면형이
     있으면 → 키워드로 해충 복구. action 을 믿고 pest 를 살린다.
       - 질문형("모기 어떻게 없애요?"): 제보 프레임이 아니라 pest 모델이 none → guide 로 복구.
       - 희석형("말벌집이 너무 많이 생겼습니다"): bag-of-words 평균이 '너무 많이'·격식체
         '생겼습니다' 같은 토큰에 희석돼 실제 제보를 none 으로 흘림 → emergency/dispatch 로 복구.
         (guide 한정이면 이 케이스가 '해충 무관'까지 새던 사각지대였음)
  ② 실제 해충(pest≠none) 제보인데 action 이 none 으로 샌다(템플릿 밖 OOD 자연 표현).
     pest 가 실제 해충이면 제보로 보는 게 안전 → none 대신 dispatch 로 강등 방지. pest 를 믿는다.

순수함수 + `predict.normalize_text` 만 의존(모델·네트워크 없음).
회귀 검증은 `eval_action.py` 의 seam probe.
"""
import predict as P

# 원문 표면형 → 라벨 (guide 질문 복구용). normalize_text 후 부분일치.
PEST_SURFACE = {
    "모기": "mosquito", "바퀴벌레": "cockroach", "러브버그": "lovebug",
    "말벌": "wasp", "빈대": "bedbug", "진드기": "tick",
}


def recover_pest_from_text(msg: str) -> str:
    """원문에서 해충 표면형을 찾아 라벨 복구. 없으면 'none'."""
    norm = P.normalize_text(msg)
    for surface, label in PEST_SURFACE.items():
        if surface in norm:
            return label
    return "none"


def correct_seam(msg: str, pest_en: str, action: str):
    """이음새 보정 ①②를 적용. 반환: (pest_en, is_real, action).

    호출 측 상태에 무관하게 안전하다 — pest≠none 으로 들어오면 ①은 자동으로 비활성
    (이미 해충이 잡혀 복구할 게 없음)이고 ②만 적용된다.
    """
    # ① action 은 해충 action(≠none)인데 pest 만 none → 원문 키워드로 해충 복구.
    #    guide 질문뿐 아니라 emergency/dispatch 도 포함(희석형 false-none 방지).
    if pest_en == "none" and action != "none":
        recovered = recover_pest_from_text(msg)
        if recovered != "none":
            pest_en = recovered
    # ② 실제 해충인데 action 이 none 으로 샘 → dispatch
    if pest_en != "none" and action == "none":
        action = "dispatch"
    return pest_en, pest_en != "none", action


if __name__ == "__main__":
    # (msg, pest_in, action_in, 기대 pest_out, 기대 action_out)
    cases = [
        ("모기 어떻게 없애요?", "none", "guide", "mosquito", "guide"),        # ① 질문형 복구
        ("동국대학교에 말벌집이 너무 많이 생겼습니다.", "none", "emergency", "wasp", "emergency"),  # ① 희석형 복구(리포트 케이스)
        ("스타필드 안성에 모기 많아요", "mosquito", "none", "mosquito", "dispatch"),  # ② none→dispatch
        ("오늘 날씨 좋네요", "none", "none", "none", "none"),                 # 보정 없음
        ("천안캠퍼스에 말벌집", "wasp", "emergency", "wasp", "emergency"),     # 그대로
        ("말벌 같은 상사 때문에 힘들어요", "none", "none", "none", "none"),     # action none → 복구 안 함(과복구 방지)
    ]
    ok = True
    for msg, pest, act, exp_p, exp_a in cases:
        p, ir, a = correct_seam(msg, pest, act)
        mark = "OK " if (p == exp_p and a == exp_a) else "FAIL"
        if mark == "FAIL":
            ok = False
        print(f"{mark} ({p},{a}) 기대=({exp_p},{exp_a})  ← {msg}")
    print("ALL PASS" if ok else "SOME FAILED")
