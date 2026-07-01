# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 상위 `Hoseo/CLAUDE.md`(대회 규칙)·루트 `Second-Brain-Project/CLAUDE.md`(위키)와는 **별개**다.
> 이 폴더(`pest-sns`)는 한국어 SNS 제보 문장 → 해충 분류 + 지도 데모 앱이다.

## 한 줄 구조

문장 입력 → **kiwi 형태소 토큰화 → TFLite 분류 → 규칙 기반 후처리(보정/오버라이드)** → 결과 + 예방카드 + 지역 지도. 모델은 의도적으로 작다(Embedding+GlobalAveragePooling bag-of-words). 오프라인 동작이 1급 제약이라 모델·토크나이저를 로컬에 동봉한다.

그 위에 **방역 추천 레이어**가 얹혀 두 Flask 앱으로 노출된다: **8600 `web/server.py`**(SNS 분석 + 지도, `/api/predict` 응답에 `advisory` 포함) · **8700 `chat_app.py`**(방역 챗 `/chat`). 두 앱은 pest 모델·action 모델·지역 해소·추천 모듈을 **그대로 공유**한다(아래 "방역 추천 서브시스템").

## 가상환경 / 명령

가상환경은 **저장소 상위의 `..\.venv`**다 (이 폴더 안이 아님). 모든 명령은 `pest-sns/`에서 실행.

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt flask==3.1.3

..\.venv\Scripts\python.exe make_train_data.py      # 학습 데이터 생성 → sample_pest_sns.csv
..\.venv\Scripts\python.exe train_to_tflite.py      # 학습 → models/ (3개 산출물)
..\.venv\Scripts\python.exe eval_holdout.py         # held-out 평가 + 회귀 (assert로 게이트)
..\.venv\Scripts\python.exe predict.py              # 빠른 추론 스모크 테스트

$env:PORT="8600"; ..\.venv\Scripts\python.exe web\server.py   # 8600 분석앱 → /, /map
..\.venv\Scripts\python.exe chat_app.py                        # 8700 방역 챗 → /, /chat, /health
..\.venv\Scripts\streamlit.exe run app.py                      # Streamlit 데모(부차적)
..\.venv\Scripts\python.exe web\build_static.py               # 정적 사이트 → web/site/
..\.venv\Scripts\python.exe deploy-hf\deploy.py               # HF Spaces 배포 (outward-facing)

# 방역/지역 관련 게이트·도구
..\.venv\Scripts\python.exe eval_action.py            # action 모델 게이트 + seam probe (assert)
..\.venv\Scripts\python.exe eval_region.py            # 지역 해소 회귀 + geocode 캐시 불변식 (assert)
..\.venv\Scripts\python.exe train_action.py          # action 모델 학습 → models/action_*
..\.venv\Scripts\python.exe make_action_data.py      # action 학습 데이터 생성
..\.venv\Scripts\python.exe backfill_geocode_regions.py [--write]   # 캐시 좌표-only 항목에 행정구역 보강
..\.venv\Scripts\python.exe build_offices.py         # data/offices.json (보건소) 재생성
```

테스트 프레임워크는 없다. **`eval_*.py`들이 사실상의 테스트**(전부 `assert` 게이트)다: `eval_holdout.py`(pest 모델 — hold-out 전부 정답 + 80%↑ 확신도 + 영어 lovebug 회귀 + 누수 검사), `eval_action.py`(action 모델 + 이음새 seam probe), `eval_region.py`(지역 해소 + 캐시 불변식). 해당 부분을 건드리면 그 게이트를 항상 돌린다.

> ⚠️ **`.py` 를 고치면 떠 있는 서버를 반드시 재시작한다 — 안 그러면 옛 코드가 그대로 응답한다.** 두 Flask 앱은 `debug=False`라 **자동 리로드가 없다.** 소스를 고쳐도 이미 실행 중인 `web/server.py`(8600)·`chat_app.py`(8700)는 **import 시점의 옛 코드를 메모리에 물고** 계속 답한다(2026-06-30 사례: `advisory.py` 를 고치고 `test_client`로 통과를 확인했지만, 사용자가 보던 떠 있는 8700 서버는 옛 코드라 그대로 오답을 냄). **`predict.py`·`advisory.py`·`recommend.py`·`region_resolve.py`·`region_detect.py`·`offices_db.py`·`*_predict.py`·`web/server.py`·`chat_app.py` 등 파이썬을 고쳤으면 → 서버 stop → 위 실행 명령 재실행 → 그 서버에 실제 입력을 넣어 확인**(`test_client`/fresh import 통과만으로 "고쳤다" 하지 말 것). 반대로 **정적 파일(`web/static/*.js·*.css`, `web/templates/*.html`)은 매 요청 새로 읽혀 재시작 불필요** — 브라우저 새로고침이면 된다.

### 로컬 키 = `.env` (`load_env.py`)
`KAKAO_REST_KEY`(장소 검색·역지오코딩)·`KAKAO_JS_KEY`(지도 SDK)는 운영 env에만 있고 로컬엔 없다. 로컬에선 **`.env`**(gitignore, `.env.example` 복사해 채움)에 넣으면 `load_env.py`가 `os.environ`에 적재한다(셸 env 우선, 네트워크 0). **주의: 키는 모듈 import 시점에 1회 읽힌다** — `region_resolve.py`·`web/server.py`가 키를 읽기 전에 `load_env`가 먼저 import돼야 해서, 두 진입점은 `load_env`를 **최상단**에서 import한다. 키 없으면 룰+캐시(오프라인)만으로 동작.

## 핵심 불변식 (어기면 조용히 망가짐)

1. **학습·추론은 같은 전처리를 공유해야 한다.** 토큰화는 `predict.py`의 `tokenize()` **단일 정의**를 `train_to_tflite.py`가 import해서 쓴다. `_KEEP_TAGS`(남길 품사), `SEQ_LEN=32`, `MAX_TOKENS=2000`을 바꾸면 **반드시 재학습**해야 하고 두 곳이 어긋나면 안 된다. `predict.load()`의 `TextVectorization`은 `standardize=None, split="whitespace"`로 vocab을 복원한다(kiwi가 이미 토큰화했으므로).

2. **`models/`는 gitignore 대상 = 재생성물.** 클론 직후엔 없다. `train_to_tflite.py`가 `pest_text_model.tflite` · `vocab.json` · `label_map.json` 3개를 만든다. `label_map.json`은 영문 라벨만 담고, 한글 표시는 `predict.KOR`에서 매핑한다.

3. **데이터 흐름은 단방향이다:**
   `sample_pest_sns_seed175.csv`(손으로 만든 까다로운 시드 **175문장**, 보존) → `make_train_data.py`가 증강·클래스 균형·누수 제거 → `sample_pest_sns.csv`(**학습 입력 ≈5,314문장**) → `train_to_tflite.py`. `sample_pest_sns.csv`를 직접 손대지 말 것 — 재생성으로 덮인다. ⚠️ **UI 캡션은 실제 학습 규모를 반영**한다 — 모델은 5,314문장으로 학습되므로 "175문장 기반"은 틀린 표기다(파일명 `seed175`의 175는 시드 수일 뿐). 현재 표기는 `index.html` foot·`app.py` 캡션 모두 "175 시드 → 5,314 증강". 행 수가 바뀌면 두 곳 같이 갱신.

## 추론 후처리 (`predict.py` — 모델 출력만으로 끝나지 않음)

작은 평균풀링 모델은 토큰 몇 개에 확률이 80%로 눌리거나 함정 문맥에 약하다. 그래서 모델 확률 위에 **규칙 레이어 3종**이 얹힌다 — 정확도 대부분이 여기서 나온다:

- `normalize_text()` — "러브 버그"/"love bug"/"말 벌" 등 표기 변형을 학습 vocab 표기로 통일. 영어 `love bug`는 **제보 문맥일 때만** 러브버그로 합침(`I love bugs`는 none).
- `calibrate_probs()` — 명확한 해충명 + 제보 문맥어가 있으면 확신도 바닥(0.85)을 보장. 단 비제보 문맥어가 섞이면 보정 안 함.
- `apply_context_overrides()` — "차량 바퀴에 벌레가 꼈다" 같은 문장을 바퀴벌레로 오인하지 않게 none으로 강제.

규칙어 사전(`_REPORT_CONTEXT_TOKENS` / `_NON_REPORT_CONTEXT_TOKENS` / 정규식들)을 고치면 `eval_holdout.py`의 회귀 케이스로 검증한다.

### 이음새(seam) 보정 단일 출처 — `advisory.py`

pest 분류와 action 분류를 이어 붙이면 생기는 두 누수를 **`advisory.correct_seam(msg, pest_en, action) → (pest_en, is_real, action)`** 한 곳에서 보정한다. `web/server.py`(8600 분석앱)·`chat_app.py`(8700 챗) **둘 다 이 함수만 호출** — 예전엔 같은 규칙이 두 파일에 복붙돼 한쪽만 고치면 조용히 갈라졌다(2026-06-30 단일화). 두 보정은 **서로 대칭**이다:

- **① pest=none & action≠none → 원문 키워드로 해충 복구** (action을 믿고 pest를 살림). guide 질문(`모기 어떻게 없애요?` — 제보 프레임이 아니라 pest 모델이 none)뿐 아니라 **희석형**(`동국대학교에 말벌집이 너무 많이 생겼습니다` — bag-of-words 평균이 `너무 많이`·격식체 `생겼습니다` 토큰에 희석돼 실제 제보를 none으로 흘림)도 복구한다. ⚠️ 2026-06-30 이전엔 이 조건이 **`action=="guide"` 한정**이라, action이 emergency/dispatch인 희석형이 복구 못 받고 `recommend`의 `pest=="none"` 가드에 걸려 **"해충 관련 내용이 아니에요"까지 새던 사각지대**였다(동국대 말벌 사례). 지금은 `action != "none"` 전체로 일반화.
- **② pest≠none & action=none → dispatch 강등 방지** (pest를 믿음). 실제 해충인데 action이 OOD 자연 표현에서 none으로 새면 none 대신 dispatch.

회귀는 `eval_action.py` seam probe + `advisory.py` 자체 self-test(`python advisory.py` → 위 두 케이스 + 과복구 방지 `말벌 같은 상사`까지 ALL PASS). **새 보정 규칙은 여기에만 추가**하고 호출부엔 두지 말 것. ⚠️ 단 이 복구는 **8700 챗에서만 사용자 응답을 고친다** — 8600 분석앱은 `build_advisory`를 `pest≠none`일 때만 호출하고 카드에 **모델 원본 확신도·후보**를 노출하므로, 같은 희석형은 8600에서 여전히 none으로 보인다(라벨만 패치하면 "89% 해충없음 + 말벌 카드" 자기모순). 8600까지 고치려면 **모델/`predict.py` 후처리 레벨**(OOD 강화·재학습)이어야 한다.

## 웹/지도 (`web/server.py`)

- Flask가 `predict.py`를 그대로 재사용. `/api/predict`(분류) · `/api/reports`(지명별 집계 마커, GET=조회/POST=사용자 제보 등록).
- 제보 데이터 = `web/data/reports.json`(가상, `make_reports.py` 생성) + `web/data/user_reports.json`(런타임 누적). 지명→좌표는 `geocode.json` 캐시 → 없으면 Kakao REST(`KAKAO_REST_KEY`) → Nominatim 순으로 조회 후 캐시.
- **불변식: geocode 캐시 항목은 좌표가 있으면 최소 시도(가능하면 시군구)도 같이 갖는다.** 지도는 좌표만 있으면 점을 찍지만 방역은 시군구가 있어야 관할 보건소를 잡는다 → '좌표만 있고 행정구역 없는' 항목은 "지도는 되는데 방역은 못 잡는" 비대칭 버그를 만든다(2026-06-30 광화문 사례). 그래서 `cache_geocode`가 좌표 적재 시 행정구역(coord2regioncode 또는 이름 룰)을 함께 저장하고, 룰 레이어(`region_detect.ALIASES`)에 핵심 랜드마크를 둔다. 시군구를 못 잡아도 `recommend`는 시도 대표 보건소로 강등한다. 기존 캐시 보강은 `backfill_geocode_regions.py`, 회귀 게이트는 **`eval_region.py`**(랜드마크 해소 + 캐시 불변식 assert).
- 지도 SDK는 `KAKAO_JS_KEY`(JavaScript 키, REST 키 아님). 없으면 `/map` 화면에서 직접 입력.
- 한글 입력 인코딩 방어: `read_json_body()`가 utf-8-sig/utf-8/cp949/euc-kr 순으로 디코드 시도(Windows 로컬 도구가 CP949로 보내는 경우 대비).

## 방역 추천 서브시스템 (8600 통합 + 8700 챗)

지도(8600)·챗(8700)이 공유하는 체인. 모듈은 **graceful import**(산출물 없으면 mock/skip)라 부분 빌드에서도 안 죽는다.

**체인:** pest(`predict.py`) + action(`action_predict.py` 모델) → 이음새 보정(`advisory.correct_seam`, §단일 출처) → **지역 해소(`region_resolve.resolve_region`)** → 추천 결합(`recommend.recommend`) → 관할 보건소(`offices_db.lookup_office`, `data/offices.json`). 8600은 `build_advisory()`가, 8700은 `/chat`이 이 체인을 호출하고 둘 다 같은 모듈을 쓴다.

### 지역 해소 = 레이어 (온라인 primary + 오프라인 안전망) — `region_resolve.py`

`resolve_region(text) → {sido, sigungu, source}`. **순서가 핵심이고, 키 유무로 갈린다:**

1. **룰(오프라인)** — `region_detect.detect_region`: 정규 시군구 직접 매칭 + `ALIASES`(랜드마크/약칭: 광화문→종로구, 해운대→해운대구 등). 잡히면 `source=rule`.
2. **장소구절 추출** — `extract_place`(8600 `extract_location`과 같은 규칙): 해충명 앞 장소를 떼어냄.
3. **캐시** — `geocode.json`에 **정밀(구 포함)** 시군구 있으면 `source=geocode-cache`(오프라인). 단 캐시 시군구가 거친 시(`용인시` 등 `coarse_cities()`)면 short-circuit 하지 않고 4번으로 내려가 구까지 정밀화한다(아래 "거친 시 정밀화"가 캐시 레이어에도 적용 — 캐시도 예외 아님).
4. **라이브(키 필요)** — Kakao keyword 검색 → 좌표 → Kakao `coord2regioncode` → 시군구. 성공 시 **캐시에 적재**(`source=geocode`)해 **다음부턴 오프라인**.

즉 **Kakao가 임의 장소의 primary**이고(키 있을 때), 룰+캐시는 **대체가 아니라 키 없을 때의 오프라인 안전망**이다. 한 번 라이브 해소된 장소는 캐시로 내려와 키 없이도 된다. 손으로 `ALIASES`를 늘리는 건 키 없는 환경(평가서버·데모)을 위한 보강일 뿐.

핵심 함정: **이름에 지역이 박혀도 좌표가 진실**이다(예: "서울대공원"은 실제 **과천시** — 룰/이름으로는 서울로 오인, Kakao 좌표는 과천으로 교정). 그래서 라이브 경로가 룰보다 정확할 수 있다.

**거친 시(구 가진 일반시) 정밀화 — 룰을 그냥 믿으면 구가 빠진다 (2026-06-30 단국대 천안캠 사례).** 룰이 "단국대학교 천안캠퍼스"에 박힌 "천안"을 잡아 **`천안시`(구 없음)** 로 short-circuit 하면, 보건소는 `천안시 동남구`/`서북구`처럼 **구 단위로 등록**돼 있어 관할을 정확히 못 짚는다(`lookup_office` 포함매칭이 동남구를 *우연히* 집어 조용히 틀릴 수 있음). 그래서 `resolve_region`은 **룰 시군구가 `offices_db.coarse_cities()`(= offices.json 의 `X시 Y구` 패턴에서 자동 도출: 천안·수원·용인·청주·성남·고양·안양·안산·전주·포항)에 들면 short-circuit 하지 않고** 좌표→`coord2regioncode`로 **구까지 정밀화**한다(`source=geocode`). 정밀화 실패(오프라인·랜드마크 없음)면 룰의 거친 시로 폴백(`source=rule`). 8600(`web/server.py`)·8700(`region_resolve.py`) **둘 다** 같은 `coarse_cities()`를 쓴다. 회귀: `eval_region.py`(coarse 집합 도출 + 오프라인 폴백 보건소 연결 assert).

**같은 불변식이 캐시·룰·라이브 세 레이어 모두에 걸린다.** 룰뿐 아니라 **캐시에 거친 시군구가 들어 있어도**(`용인시`처럼 구 없는) 그대로 반환하지 않고 좌표로 정밀화한다. 그래서 `geocode.json`에 거친 시 엔트리가 쌓이면 안 된다 — **랜드마크 키는 항상 구까지** 적재한다(예외: `천안시`·`충청남도 천안시`처럼 **이름 자체가 시 단위**인 bare 키는 '구 모름'이 정직하므로 거친 채로 둔다). 캐시가 거친데 정밀화도 실패하면(오프라인) 거친 캐시값으로 폴백한다. ⚠️ 단순 이름 룰(`region_from_name`)로 좌표를 캐시에 적재하는 경로(`cache_geocode`)는 키 없을 때 거친 시를 만들 수 있다 → 그건 라이브 해소 시 자동 정밀화돼 self-heal 된다.

### 관할 보건소는 거리가 아니라 행정구역 기준

`recommend` → `offices_db.lookup_office(sigungu, sido)`: **시군구 이름 매칭**으로 관할 보건소를 찾는다(가장 가까운 보건소가 아님 — 옆 구의 더 가까운 보건소를 잡으면 관할이 틀린다). `좌표→시군구→이름매칭`이 정석. `offices.json`엔 좌표가 없어 거리탐색 자체가 불가하기도 하다. 시군구를 못 잡고 **시도만** 있으면 `recommend`가 시도 대표 보건소로 **강등**한다(아무 안내도 못 주는 것보다 낫게). 번호는 CSV 원본만(추측 0).

## 두 배포 경로 (서로 다른 추론 위치)

| 경로 | 추론 | 빌드/배포 | 산출물 |
|------|------|-----------|--------|
| **HF Spaces (Flask)** | 서버에서 tflite | `deploy-hf/deploy.py` → `.hfspace/` staging 조립 후 업로드 | 라이브 앱 |
| **Cloudflare Pages (정적)** | **브라우저**에서 (`web/site/static/infer.js` + `data/model.json`) | `web/build_static.py` → `web/site/` | `markers.json` 미리 집계 |

`deploy-hf/deploy.py`는 앱 구동에 필요한 파일만 골라 `.hfspace/`에 복사한다(`app.py`·학습 스크립트·csv·로그 제외). `.hfspace/`는 재생성물이므로 직접 수정 금지. HF 배포는 outward-facing이니 사용자 요청 시에만.
