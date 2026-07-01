# D — 데이터: 전국 보건소 표준데이터 ingest

너는 방역 추천 에이전트 **Phase2 D(데이터) 세션**이다. `CONTRACTS.md`를 읽고, 네 소유 파일만 쓴다.
작업 디렉토리: `Hoseo/pest-sns`. venv: `../.venv/Scripts/python.exe`.

## 전제 (사용자가 먼저 줌)
`data/health_orgs_raw.csv` = 공공데이터포털 **전국보건기관표준데이터**(data.go.kr/15107750) CSV.
- ⚠ 인코딩이 **EUC-KR(cp949)** 일 가능성 큼 → `cp949` 먼저, 실패 시 `utf-8-sig` 폴백으로 읽어라.
- 컬럼: 보건기관명, 시도명, 시군구명, 보건기관유형명, 소재지도로명주소, 전화번호, 데이터기준일자 등.

## 목표
시군구 단위 보건소 룩업 인프라. 손으로 번호 채우지 말고 **CSV에 있는 값만** 쓴다(추측 0).

## 소유 파일 (이것만 쓰기)
`build_offices.py` · `data/offices.json` · `offices_db.py`

## 단계
1. `build_offices.py`: CSV 읽어 **보건기관유형명이 '보건소' 또는 '보건의료원'** 인 행만 추려
   `data/offices.json` 생성:
   ```json
   {"_source":"전국보건기관표준데이터 data.go.kr/15107750 (다운로드 YYYY-MM-DD)",
    "offices":[{"name":"천안시 동남구보건소","tel":"041-521-2651","sido":"충청남도",
                "sigungu":"천안시 동남구","addr":"..."}]}
   ```
   - tel은 CSV 원본 그대로. 빈 값이면 `""`. 시군구명 정규화(공백 정리)만.
2. `offices_db.py` (계약 — wiring이 import):
   ```python
   def lookup_office(sido=None, sigungu=None) -> dict:
       """sigungu 우선 매칭 → {"name","tel","sido","sigungu","addr"} | {} (없으면).
          sigungu 없고 sido만 오면 그 시도 대표 1곳."""
   def region_names() -> dict:
       """{"sido":[고유 시도명...], "sigungu":[고유 시군구명...]} — R이 매칭에 씀."""
   ```

## DONE 체크
```bash
../.venv/Scripts/python.exe -c "import offices_db as o; \
print(len(o.region_names()['sigungu']),'개 시군구'); \
print(o.lookup_office(sigungu='천안시 동남구')); \
print(o.lookup_office(sigungu='부산 해운대구') or o.lookup_office(sido='부산광역시'))"
# 기대: 200+ 시군구, 천안/부산 보건소 실제 번호 출력
```
통과하면 STATUS `D ✅ <명령> → N개 시군구, 실번호 확인`. 막히면 `D ⛔ <사유>`.
