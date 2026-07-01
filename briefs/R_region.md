# R — 지역 감지 모듈

너는 방역 추천 에이전트 **Phase2 R(지역감지) 세션**이다. `CONTRACTS.md`를 읽고, 네 소유 파일만 쓴다.
작업 디렉토리: `Hoseo/pest-sns`. **D를 안 기다린다** — mock 지역명 목록으로 t=0 시작.

## 목표
자유 한국어 메시지 → 행정구역(시도/시군구) 추출. "단국대 천안캠퍼스" → 천안시, "해운대에 말벌집" → 부산 해운대구.

## 소유 파일 (이것만)
`region_detect.py`

## 계약 (wiring이 import)
```python
def detect_region(text) -> dict:
    """반환: {"sido": str|None, "sigungu": str|None}. 못 찾으면 둘 다 None.
       - 시군구명/시도명 직접 매칭 + 별칭(천안캠퍼스/천안캠→천안시, 해운대→해운대구,
         강남→강남구 등) + 동/역명 일부도 가능하면 매핑."""
```

## 방식
- 정규 지역명 목록은 **D의 `offices_db.region_names()`** 가 출처(integration 때 연결).
  지금은 mock 목록으로 개발:
  ```python
  try:
      from offices_db import region_names
      _NAMES = region_names()
  except Exception:
      _NAMES = {"sido": ["충청남도","서울특별시","부산광역시"],
                "sigungu": ["천안시 동남구","천안시 서북구","강남구","해운대구"]}
  ```
- 매칭: 긴 이름 우선(부분문자열), 별칭 dict 별도. 과매칭 주의("서울 얘기"만으로 특정 구 단정 X → 시도만).

## DONE 체크
```bash
../.venv/Scripts/python.exe -c "from region_detect import detect_region as d; \
print(d('단국대 천안캠퍼스에 말벌집')); print(d('해운대에 모기 너무 많아요')); \
print(d('오늘 점심 뭐먹지'))"
# 기대: 천안 관련 sigungu / 부산 해운대 / {None,None}
```
통과하면 STATUS `R ✅ <명령> → 천안·해운대 감지/잡담 None`. 막히면 `R ⛔ <사유>`.
