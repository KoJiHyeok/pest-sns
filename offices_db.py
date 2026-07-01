"""offices_db.py — 보건소 룩업 (Phase2 D 소유, wiring/R 이 import)

계약(CONTRACTS.md §Phase2):
    lookup_office(sido=None, sigungu=None) -> dict   # {"name","tel","sido","sigungu","addr"} | {}
    region_names() -> dict                            # {"sido":[...], "sigungu":[...]}

데이터 출처: data/offices.json (build_offices.py 생성). 번호는 CSV 원본만(추측 0).
"""
import json
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "offices.json"
_CACHE = None


def _load():
    global _CACHE
    if _CACHE is None:
        with _DATA.open(encoding="utf-8") as f:
            _CACHE = json.load(f).get("offices", [])
    return _CACHE


def _norm(s: str) -> str:
    """매칭용 정규화: 공백 전부 제거. '부산 해운대구' == '해운대구'+'부산' 류 흡수."""
    return "".join((s or "").split())


def lookup_office(sido=None, sigungu=None) -> dict:
    """sigungu 우선 매칭 → 보건소 1곳. 없으면 sido 대표 1곳. 둘 다 없으면 {}.

    매칭 단계(sigungu):
      1) 공백 제거 후 완전 일치
      2) 포함 관계(양방향) — '부산해운대구' ⊇ '해운대구' 같은 경우 흡수
    """
    offices = _load()

    if sigungu:
        q = _norm(sigungu)
        if q:
            for o in offices:                       # 1) 정확 일치
                if _norm(o["sigungu"]) == q:
                    return o
            if len(q) >= 2:                          # 2) 포함 관계
                for o in offices:
                    os = _norm(o["sigungu"])
                    if os and len(os) >= 2 and (os in q or q in os):
                        return o

    if sido:
        qs = _norm(sido)
        if qs:
            for o in offices:                       # 시도 대표 1곳
                d = _norm(o["sido"])
                if d and (d == qs or d in qs or qs in d):
                    return o

    return {}


def region_names() -> dict:
    """매칭에 쓸 고유 시도·시군구 이름 목록(정렬)."""
    offices = _load()
    sido = sorted({o["sido"] for o in offices if o["sido"]})
    sigungu = sorted({o["sigungu"] for o in offices if o["sigungu"]})
    return {"sido": sido, "sigungu": sigungu}


_COARSE = None


def coarse_cities() -> set:
    """행정구(일반구)를 가진 '구 없는 시' 이름 집합(예: {'천안시','수원시',...}).

    보건소는 '천안시 동남구'처럼 구 단위로 등록돼 있어, 룰이 '천안시'까지만 잡으면
    관할 보건소를 정확히 못 짚는다(구가 빠짐). 이 집합에 든 시는 룰 결과가 '거칠다'고 보고
    좌표→구까지 정밀화해야 한다. 데이터(offices.json)에서 'X시 Y구' 패턴으로 자동 도출."""
    global _COARSE
    if _COARSE is None:
        coarse = set()
        for o in _load():
            parts = (o.get("sigungu") or "").split()
            if len(parts) >= 2 and parts[0].endswith("시") and parts[-1].endswith("구"):
                coarse.add(parts[0])
        _COARSE = coarse
    return _COARSE


if __name__ == "__main__":
    names = region_names()
    print(len(names["sigungu"]), "개 시군구 /", len(names["sido"]), "개 시도")
    print("해운대 :", lookup_office(sigungu="부산 해운대구") or lookup_office(sido="부산광역시"))
    print("천안   :", lookup_office(sigungu="천안시 동남구"))
