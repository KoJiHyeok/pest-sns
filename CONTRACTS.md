# CONTRACTS.md — 방역 추천 에이전트 (4세션 단일 출처)

> 이 문서는 **법(law)**이다. 4개 세션(S1~S4)은 자기 영역만 건드리고, 아래 계약(인터페이스)은
> **임의로 바꾸지 않는다.** 바꿔야 하면 STATUS에 `⚠ 계약변경 제안`을 남기고 전체 합의 후 수정.
> 목표: 해충 상황 텍스트 → ① 무슨 해충 ② 어떤 Action ③ 어디 연락(관공서) 을 챗으로 응답.

---

## 0. 라벨 집합 (고정 — 누구도 안 바꿈)

```
pest   = mosquito | cockroach | lovebug | wasp | tick | bedbug | none   (기존 모델, models/label_map.json)
action = emergency | dispatch | guide | none                            (★ 새 모델 S1이 생성)
```

- `pest == "none"` = 해충 제보 아님(=is_real False).
- `pest_info.json` 키는 none 제외 6종(lovebug, wasp, tick, mosquito, cockroach, bedbug).

### action 의미 + 라벨링 기준(권장)
| action | 의미 | 트리거 맥락(데이터 라벨링 힌트) |
|--------|------|--------------------------------|
| `emergency` | 즉시 행동 필요 | 쏘임·물려서 부음·호흡곤란·말벌집/벌집 발견 (주로 wasp·심한 bedbug/tick) |
| `dispatch` | 방역/신고 연결 | 대량 출몰("너무 많아요/떼/들끓")·"방역 필요"·"신고"·단순 목격 제보 기본값 |
| `guide` | 정보·예방 안내 | 질문형("어떻게 없애요?/예방법/왜 생겨요?") |
| `none` | 해충 무관 | 잡담·영화/노래/회상·애정표현·중립 문장 |

---

## 1. 계약 ① action 분류기   (S1 → S4)

파일: `action_predict.py` (predict.py 골격 재사용, **tokenize는 predict.py 것 import**)

```python
LABELS = ["emergency", "dispatch", "guide", "none"]

def load_action():
    """models/action_vocab.json + action_label_map.json + action_model.tflite 로드.
    반환: (vectorizer, interp, label_map)  — predict.load() 와 동일 패턴."""

def predict_action(text, vectorizer, interp, label_map) -> dict:
    """반환: {"action": "<LABELS 중 1>", "probs": {"emergency":0.., ...}}"""
```

산출물(전부 S1 소유, `models/` 에 둠): `action_model.tflite`, `action_vocab.json`, `action_label_map.json`

---

## 2. 계약 ② 추천 결합   (S2 → S4)   ※모델 불필요, 순수함수

파일: `recommend.py` — `pest_info.json`(읽기) + `offices.json`(S2가 작성) 결합

```python
def recommend(pest: str, is_real: bool, action: str, location: str = "") -> dict:
    """반환(이 모양 고정):
    {
      "reply":   "<챗에 그대로 뿌릴 완성 텍스트>",   # 줄바꿈 \n 포함, 렌더 책임은 S2
      "headline":"[긴급] 말벌(위험도 高) ...",
      "pest_kor":"말벌",
      "level":   "high|medium|low|none",
      "steps":   ["...", "..."],
      "office":  {"name":"천안시 동남구보건소","tel":"041-..."},   # 없으면 {}
      "action":  "emergency"
    }"""
```

### 결정 로직(권장 표)
| 조건 | 처리 |
|------|------|
| `action=="none"` 또는 `pest=="none"` | "해충 관련 내용이 아니에요" 안내, office={} |
| `action=="emergency"` | pest_info.caution + 119, office=긴급(119)+보건소 |
| `action=="dispatch"` | pest_info.prevention 요약, office=보건소/통합민원 |
| `action=="guide"` | pest_info.prevention+clothing, office 선택(없어도 됨) |

`level`/문구는 `pest_info[pest]`의 `level·risk·caution·prevention·clothing`에서 가져온다.

---

## 3. 계약 ③ 챗 API   (S3 ↔ S4)

```
POST /chat
요청  {"message": "단국대 천안캠퍼스에 말벌집이 생겼어요"}
응답  200 {
  "reply":  "[긴급] 말벌(위험도 高) ...\n· 즉시: ...\n· 신고: 천안시 동남구보건소 ☎ ...",
  "pest":   "wasp",
  "action": "emergency",
  "office": {"name":"천안시 동남구보건소","tel":"041-..."}
}
```

- S3은 이 응답 모양만 믿고 UI를 만든다(아래 mock 사용).
- S4는 이 라우트를 `chat_app.py`(★새 Flask, **포트 8700**)에 구현. 기존 `web/server.py`는 안 건드림.

---

## 4. 파일 소유권 (겹침 0 — 남의 칸 쓰기 금지)

| 세션 | 쓰기(소유) | 읽기(재사용·수정금지) |
|------|------------|------------------------|
| S1 ML | `make_action_data.py` `train_action.py` `action_predict.py` `models/action_*` `data/action_data.csv` | `predict.py`(tokenize) `make_train_data.py`(참고) |
| S2 도메인 | `offices.json` `recommend.py` | `pest_info.json` `models/label_map.json` |
| S3 프론트 | `web/static/chat.html` `web/static/chat.js` `web/static/chat.css` | — (mock) |
| S4 통합 | `chat_app.py` | S1 `action_predict` · 기존 `predict` · S2 `recommend` · S3 `chat.html` |

> 공유 디렉토리 + 파일 소유권 방식. `models/`엔 파일명이 `action_*`라 기존 pest 모델과 안 겹친다.
> 기존 `web/server.py`(지도앱)는 **아무도 안 건드린다.**

---

## 5. mock (서로 안 기다리고 t=0 시작)

- **S2**: 모델 없이 `recommend("wasp", True, "emergency", "천안")` 같은 하드코딩 입력으로 단독 완성·테스트.
- **S3**: `chat.js` 상단에 `const MOCK = true;` — true면 `/chat` 대신 고정 응답(계약③ 모양) 반환해 UI 완성. S4 붙으면 `false`.
- **S4**: S1·S2 done 전엔 `predict_action`/`recommend`를 가짜로 두고 라우트 골격부터. done 신호 뜨면 실물 import로 스왑.

---

## 7. Phase 2 — 전국 다지역 관공서 (gold-in-gold-out)

천안 1지역 → 전국 시군구 보건소. **손수집 X**, 공공데이터 표준데이터 ingest.
원천: 전국보건기관표준데이터 `data.go.kr/15107750` (보건기관명·시도·시군구·전화·주소).

### 파일 소유권 (겹침 0)
| 세션 | 쓰기(소유) | 비고 |
|------|------------|------|
| D 데이터 | `build_offices.py` `data/offices.json` `offices_db.py` `data/health_orgs_raw.csv` | CSV는 사용자가 받아둠 |
| R 지역감지 | `region_detect.py` | mock-first, integration 때 D 연결 |
| E 평가 | `eval_action.py` | 완전 독립 |
| (wiring=S4/나) | `chat_app.py` + **`recommend.py`(이 단계 동안 S4가 인수)** | D·R ✅ 후 |

### 계약
```python
# D → wiring
def lookup_office(sido=None, sigungu=None) -> dict   # {"name","tel","sido","sigungu","addr"} | {}
def region_names() -> dict                            # {"sido":[...], "sigungu":[...]}
# R → wiring
def detect_region(text) -> dict                       # {"sido":str|None, "sigungu":str|None}
# wiring: chat_app 가 detect_region(msg)→sigungu 를 recommend(...,location=sigungu) 로,
#         recommend 는 offices_db.lookup_office(sigungu=location) 로 관할 보건소 주입.
#         지역 미감지 시 "지역을 알려주시면 관할 보건소 안내" 폴백.
```
⚠ 번호는 CSV 원본만(추측 0). 빈 값은 `""`. recommend.py 는 이 단계엔 **wiring만** 수정(천안 하드코딩 제거).

---

## 6. STATUS (각 세션이 끝나면 한 줄 추가 — done 신호)

형식: `S# ✅  <검증 명령어> → <기대 결과>`  /  막히면 `S# ⛔ <사유>`

<!-- 아래에 append -->
- S1 ✅  `python -c "import action_predict as A; L=A.load_action(); fn=lambda t: A.predict_action(t,*L)['action']; print(fn('단국대 천안캠퍼스에 말벌집이 생겼어요'), fn('러브버그 너무 많아요'), fn('모기 어떻게 없애요?'), fn('오늘 날씨 좋네요'))"` → emergency dispatch guide none
- S2 ✅  `python -c "from recommend import recommend as r; print(r('wasp',True,'emergency','천안')['reply'])"` → 말벌 긴급(119+보건소)/러브버그 물뿌리기/해충무관 3케이스 정상. offices.json 천안 실값(보건소 041-521-2651·콜센터 1422-36·119) 확인 완료.
- S3 ✅  web/static/chat.html 직접 열기(MOCK=true) → 말풍선 렌더 + \n 유지 + 관공서 tel: 링크 정상
- S4 ✅  `python chat_app.py` → localhost:8700 E2E 6케이스 정상(말벌 긴급/러브버그 신고/모기·러브버그 guide/바퀴 신고/잡담 none), action·recommend·pest 전부 real, 오프라인 동작(네트워크 호출 0).
  - 통합 중 발견·수정: ① 이음새 버그 — guide 질문을 pest 모델이 none으로 봐 반려되던 것을 chat_app에서 키워드 복구로 보정. ② chat.js `MOCK=false`로 전환(계약 113 합의된 S4 연결 단계). ③ 정적파일 route 누락(chat.js/css 404) → Flask static_folder 설정으로 수정.
- ── Phase 2 ──
- D ✅  `../.venv/Scripts/python.exe -c "import offices_db as o; print(len(o.region_names()['sigungu'])); print(o.lookup_office(sigungu='천안시 동남구')); print(o.lookup_office(sigungu='부산 해운대구'))"` → **224개 시군구**, 천안시동남구보건소 041-521-2650 · 해운대구보건소 051-746-4000 실번호. 전국 CSV(3598행, 보건소/보건의료원 259곳) 빌드. build_offices.py는 구/신 표준 컬럼 둘 다 지원(별칭매핑: 기관유형/보건기관유형명, 대표 전화번호/전화번호 등). 번호 CSV 원본만(추측0, 빈값 "").
- R ✅  `../.venv/Scripts/python.exe -c "from region_detect import detect_region as d; print(d('단국대 천안캠퍼스에 말벌집')); print(d('해운대에 모기 너무 많아요')); print(d('오늘 점심 뭐먹지'))"` → 천안(충청남도/천안시)·부산 해운대(부산광역시/해운대구)·잡담(None/None). D의 offices_db.region_names() 실연결 완료(import 성공 시 실데이터, 실패 시 mock). 정규명 직접매칭(뒤토큰·시/군 어간 포함) 우선 + 별칭(천안캠퍼스/해운대/강남…) 폴백 + 시군구기반 sido 추론('해운대구'→부산, '대구' 부분문자열 오매칭 방지). 천안은 D 부분샘플에 없어 별칭이 채움 — 전국 CSV 재빌드 시 정규명 직접매칭으로 자동 승격(코드수정 0).
- E ✅  `../.venv/Scripts/python.exe eval_action.py` → 홀드아웃(seed42 tail 20%, 누수0 assert 통과) accuracy=99.8%(417/418), 클래스별 P/R + 혼동행렬 + 이음새 probe 출력. **약점: 99.8%는 증강 템플릿 내부(in-distribution)라 부풀려진 값 — 템플릿 밖 자연 표현 guide질문 1/8이 none으로 샘(seam 88%). 진짜 일반화는 OOD에서 더 낮음. 키워드복구 band-aid가 메우는 게 바로 이 누수.**
- wiring(S4) ✅  recommend.py(offices.json 천안하드코딩 제거 → `offices_db.lookup_office(sigungu=location)` 전국 룩업, 119 공통, 보건소 미발견 시 "지역 알려주세요" 넛지·추측0) + chat_app.py(`detect_region(msg)`→시군구를 recommend에 주입, graceful import). E2E: "부산 해운대 말벌집"→해운대구/부산→**해운대구보건소 051-749-4000** 실번호, /health action·recommend·region 전부 real. 강남·천안은 부분CSV에 없어 office 공란(코드 OK, 전국 CSV 재빌드 시 0코드 자동 충족).
- ⚠ 데이터 액션(D 후속): 그리드 다운로드는 부분샘플 함정. **전체는 [보건복지부 전국 지역보건의료기관 현황](https://www.data.go.kr/data/3072692/fileData.do)** — 파일데이터, 3,598기관 전수, CSV, 로그인X, 컬럼(시도·시군구·보건기관명·기관유형·대표전화번호). 이걸 `data/health_orgs_raw.csv`로 덮고 `build_offices.py` 재실행. ※컬럼명이 15107750과 다를 수 있어 D가 매핑 한 번 확인(유형='보건소' 필터, cp949 인코딩).
- ✅ **전국판 완성** (전체 CSV 재빌드 후 wiring E2E): 천안캠퍼스→천안시동남구보건소 041-521-2650 · 강남→강남구보건소 02-3423-7200 · 해운대→해운대구보건소 051-746-4000 · 수원 권선구→권선구보건소 031-228-6266 · 제주 노형동→제주시제주보건소 064-728-4000 · 잡담→none. 코드수정 0(전부 offices_db 경유).
  - ⚠ 데이터 vintage caveat: 같은 정부 출처라도 값이 갈림 — 해운대구보건소가 표준데이터(15107750)=051-749-4000 vs 파일데이터(3072692, 2022기준)=051-746-4000. 현재는 후자 사용. **고빈도 보건소 몇 곳은 현행 공식페이지로 spot-check 권장**(번호 신뢰=에이전트 신뢰).
- ── Phase 3 — 8600 앱 통합(첫 SNS앱 + 방역 도우미) ──
- ✅ 챗(8700) 지역해소 패리티: 룰만 쓰던 chat_app을 공용 `region_resolve.py`(룰→장소추출→좌표→Kakao coord2regioncode→시군구, 캐시 적재)로 교체. 챗·분석앱이 같은 모듈 공유. KAKAO_REST_KEY 있으면 신규 랜드마크 라이브 해소(없으면 룰+캐시).
  - 라이브 검증(키 set): "벡스코"→해운대구보건소(geocode 라이브), "롯데월드타워"→송파구보건소(geocode). 한번 해소되면 캐시→오프라인.
  - 이음새 보정②: action 모델이 OOD 문장("스타필드 안성에 모기 많아요")을 none으로 오분류 → pest≠none이면 action을 dispatch로 보정(false-none 방지). pest=none(잡담)은 안 건드림. chat_app + web/server 양쪽 적용.
- ✅ 8600 "AI로 분석"에 방역 도우미 통합. web/server.py: action_predict·region_detect·recommend graceful import + `resolve_region`(룰→지오코딩 좌표→Kakao coord2regioncode→시군구, 결과 캐시 적재로 다음엔 오프라인) + `build_advisory` → `/api/predict` 응답에 `advisory{action,region,office,reply,steps}` 추가. app.js render에 방역 도우미 카드(action 뱃지·관할 보건소 tel링크). E2E(키 없는 인스턴스): "강남 말벌집"→강남구보건소(rule), "서울 코엑스 말벌"→**강남구보건소(geocode-cache)**, 잡담→advisory 없음. 코엑스는 좌표캐시에 시군구 시딩(좌표=강남 삼성동, 추측0). ⚠ 신규 미캐시 랜드마크 라이브 해소는 KAKAO_REST_KEY 필요(8600 운영 env엔 있음).
