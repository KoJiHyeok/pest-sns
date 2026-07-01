# -*- coding: utf-8 -*-
"""CONTRACTS.md 계약② + Phase2 wiring — 추천 결합 (순수함수, 모델 불필요).

pest + action + location(시군구)을 받아 대응 가이드 + 관할 보건소 연결 dict를 만든다.
- pest_info.json (읽기): level·risk·caution·prevention·clothing
- offices_db (Phase2 D): 전국 시군구 보건소 룩업 (data/offices.json) — 번호는 CSV 원본(추측 0)
- 119는 전국 공통(긴급)
location 은 region_detect 가 뽑은 시군구명을 chat_app 이 주입한다. 빈 값이면 보건소 미지정.
렌더(완성 텍스트 `reply`) 책임은 여기에 있다.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_PEST_INFO = json.loads((HERE / "pest_info.json").read_text(encoding="utf-8"))

try:
    import offices_db  # Phase2 D — 전국 보건소 룩업 (없어도 동작: 보건소 미지정)
except Exception:
    offices_db = None

# 영문 pest → 한글 (models/label_map.json은 영문만 담음 → 표시용 매핑)
KOR = {
    "none": "해충 없음", "lovebug": "러브버그", "mosquito": "모기",
    "cockroach": "바퀴벌레", "bedbug": "빈대", "wasp": "말벌", "tick": "진드기",
}

# pest_info의 level 표기(high/mid/low) → 계약② 표기(high|medium|low|none) + 한글 위험도
_LEVEL_NORM = {"high": "high", "mid": "medium", "medium": "medium", "low": "low"}
_LEVEL_KOR = {"high": "高", "medium": "中", "low": "低", "none": "—"}
_ACTION_TAG = {"emergency": "긴급", "dispatch": "신고", "guide": "안내", "none": "안내"}
_EMER = {"name": "119", "tel": "119"}
_ASK_REGION = "지역(시/군/구)을 알려주시면 관할 보건소 연락처를 안내해 드려요."


def _bohgeon(location: str, sido: str = "") -> dict:
    """시군구 → 관할 보건소. 시군구가 없으면 시도 대표 보건소로 강등(추측 0, 데이터 매칭만).

    시군구를 못 잡아도(랜드마크 좌표만 있는 경우 등) 최소 시도 단위 보건소는 안내해
    '지도는 찍히는데 방역은 못 잡는' 비대칭을 없앤다.
    """
    if offices_db is None or (not location and not sido):
        return {}
    o = offices_db.lookup_office(sigungu=location or None, sido=sido or None)
    if not o:
        return {}
    return {"name": o.get("name", "관할 보건소"), "tel": o.get("tel") or "확인필요"}


def _render(headline: str, steps: list, office: dict) -> str:
    """챗에 그대로 뿌릴 완성 텍스트: 헤드라인 + · 불릿 + 관공서 ☎."""
    lines = [headline]
    lines += [f"· {s}" for s in steps]
    if office:
        lines.append(f"☎ {office['name']} {office['tel']}")
    return "\n".join(lines)


def recommend(pest: str, is_real: bool, action: str, location: str = "", sido: str = "") -> dict:
    """계약② 반환 모양 고정. CONTRACTS 2절 결정 로직을 따른다."""
    # ── 해충 무관 ────────────────────────────────────────────────
    if action == "none" or pest == "none" or not is_real:
        headline = "[안내] 해충 관련 내용이 아니에요"
        steps = [
            "해충 제보나 방제 질문을 보내주시면 위험도·대응법·관할 연락처를 안내해 드려요.",
            "예) “천안캠퍼스에 말벌집이 생겼어요”, “러브버그 어떻게 없애요?”",
        ]
        return {
            "reply": _render(headline, steps, {}),
            "headline": headline,
            "pest_kor": KOR.get(pest, "해충 없음"),
            "level": "none",
            "steps": steps,
            "office": {},
            "action": "none",
        }

    info = _PEST_INFO.get(pest, {})
    pest_kor = KOR.get(pest, pest)
    level = _LEVEL_NORM.get(info.get("level", ""), "none")
    risk_kor = _LEVEL_KOR[level]
    tag = _ACTION_TAG.get(action, "안내")
    headline = f"[{tag}] {pest_kor}(위험도 {risk_kor})"

    bohgeon = _bohgeon(location, sido)

    # ── emergency: 응급조치 + 119(전국 공통) + 관할 보건소 ────────
    if action == "emergency":
        steps = []
        if info.get("caution"):
            steps.append(info["caution"])
        steps.append(f"즉시 위험 시 119 신고 — {_EMER['name']} ☎ {_EMER['tel']}")
        if bohgeon:
            steps.append(f"방제·민원은 {bohgeon['name']} ☎ {bohgeon['tel']}")
        else:
            steps.append(_ASK_REGION)
        office = bohgeon or _EMER

    # ── dispatch: 예방 요약 + 방역 신고 연결 ─────────────────────
    elif action == "dispatch":
        steps = []
        if info.get("prevention"):
            steps.append(info["prevention"])
        if bohgeon:
            steps.append("대량 출몰·방역이 필요하면 관할 보건소로 신고하세요.")
        else:
            steps.append("대량 출몰·방역이 필요하면 관할 보건소로 신고하세요. " + _ASK_REGION)
        office = bohgeon

    # ── guide: 예방 + 복장 + 기피제 안내 ─────────────────────────
    else:  # guide
        steps = []
        if info.get("prevention"):
            steps.append(info["prevention"])
        if info.get("clothing"):
            steps.append(f"복장: {info['clothing']}")
        if info.get("repellent"):
            steps.append(f"기피제: {info['repellent']}")
        office = bohgeon  # 선택 — 더 알아보고 싶을 때 관할 보건소 연락처

    return {
        "reply": _render(headline, steps, office),
        "headline": headline,
        "pest_kor": pest_kor,
        "level": level,
        "steps": steps,
        "office": office,
        "action": action,
    }


if __name__ == "__main__":
    for args in [("wasp", True, "emergency", "부산 해운대구"),
                 ("mosquito", True, "guide", "천안시 동남구"),
                 ("lovebug", True, "dispatch", ""),
                 ("none", False, "none", "")]:
        print(recommend(*args)["reply"])
        print("---")
