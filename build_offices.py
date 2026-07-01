"""build_offices.py — 전국보건기관표준데이터 CSV → data/offices.json (Phase2 D 소유)

원천: 전국보건기관표준데이터 data.go.kr/15107750
- CSV(data/health_orgs_raw.csv)에서 보건기관유형명이 '보건소' 또는 '보건의료원'인 행만 추린다.
- tel·addr 등은 CSV 원본 그대로(추측 0). 빈 값은 "".
- 시군구명·시도명은 공백 정리만 한다(정규화).

실행: ../.venv/Scripts/python.exe build_offices.py
"""
import csv
import json
import datetime
from pathlib import Path

RAW = Path("data/health_orgs_raw.csv")
OUT = Path("data/offices.json")
KEEP_TYPES = {"보건소", "보건의료원"}

# 컬럼명은 다운로드 시점/버전에 따라 다르다(구 표준 vs 신 표준). 별칭 후보를 순서대로 찾는다.
COLS = {
    "name": ("보건기관명",),
    "tel": ("대표 전화번호", "전화번호"),
    "sido": ("시도명", "시도"),
    "sigungu": ("시군구명", "시군구"),
    "addr": ("소재지도로명주소", "주소"),
    "type": ("보건기관유형명", "기관유형"),
}


def _read_rows():
    """cp949 먼저, 실패 시 utf-8-sig 폴백으로 CSV를 읽는다."""
    last = None
    for enc in ("cp949", "utf-8-sig"):
        try:
            with RAW.open(encoding=enc, newline="") as f:
                return list(csv.DictReader(f)), enc
        except (UnicodeDecodeError, LookupError) as e:
            last = e
    raise RuntimeError(f"CSV 인코딩 해석 실패: {last}")


def _norm(s: str) -> str:
    """공백 정리만 — 양끝 strip + 내부 연속 공백을 하나로."""
    return " ".join((s or "").split())


def _resolve(fieldnames):
    """실제 헤더에서 각 논리필드 → 실제 컬럼명 매핑. 못 찾으면 None."""
    present = set(fieldnames or [])
    resolved = {}
    for logical, candidates in COLS.items():
        resolved[logical] = next((c for c in candidates if c in present), None)
    return resolved


def build():
    rows, enc = _read_rows()
    col = _resolve(rows[0].keys() if rows else [])
    if not col["type"] or not col["name"]:
        raise RuntimeError(f"CSV 컬럼을 못 찾음(유형/기관명). 실제 헤더: {list(rows[0].keys()) if rows else []}")

    def g(r, logical):
        c = col[logical]
        return _norm(r.get(c, "")) if c else ""

    offices = []
    for r in rows:
        if g(r, "type") not in KEEP_TYPES:
            continue
        offices.append({
            "name": g(r, "name"),
            "tel": g(r, "tel"),          # CSV 원본 그대로(빈 값이면 "")
            "sido": g(r, "sido"),
            "sigungu": g(r, "sigungu"),
            "addr": g(r, "addr"),
        })

    # 데이터기준일자 중 최신값(있을 때만 — 신 표준 CSV엔 없음)
    data_dates = [_norm(r.get("데이터기준일자", "")) for r in rows]
    data_date = max((d for d in data_dates if d), default="")
    today = datetime.date.today().isoformat()

    payload = {
        "_source": (
            "전국보건기관표준데이터 data.go.kr/15107750 "
            f"(데이터기준일자 {data_date}, 다운로드 {today}, 인코딩 {enc})"
        ),
        "_note": "보건기관유형명 '보건소'/'보건의료원' 행만. tel·addr은 CSV 원본(추측 0).",
        "offices": offices,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    sigungu_n = len({o["sigungu"] for o in offices})
    no_tel = sum(1 for o in offices if not o["tel"])
    print(f"[build_offices] {len(offices)}개 보건소 / {sigungu_n}개 시군구 → {OUT}")
    if no_tel:
        print(f"  ⚠ 전화번호 빈 값 {no_tel}건(CSV 원본 공란 — 추측으로 채우지 않음)")
    return payload


if __name__ == "__main__":
    build()
