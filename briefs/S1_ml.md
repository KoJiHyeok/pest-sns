# S1 — ML: action 분류기 (새 tflite 모델)

너는 방역 추천 에이전트의 **S1(ML) 세션**이다. 먼저 `CONTRACTS.md`를 읽고 그 계약①·라벨 기준을 법으로 따른다.
**네 칸만 쓴다**(소유 파일 외 절대 수정 금지). 작업 디렉토리: `Hoseo/pest-sns`.

## 목표
텍스트 → action(emergency·dispatch·guide·none) 4분류 tflite 모델을 **기존 파이프라인 재활용**으로 만든다.

## 단계 (테스트-먼저)
1. **데이터** `make_action_data.py`: `make_train_data.py`의 프레임/지명/문맥을 재활용하되,
   **라벨을 pest가 아니라 action으로** 매핑한다(CONTRACTS 라벨 기준 표 참고).
   - emergency: 쏘임·물려서 부음·호흡곤란·벌집/말벌집 (wasp 계열 + 심한 케이스)
   - dispatch: 대량("너무 많아요/떼/들끓")·"방역 필요"·"신고"·단순 목격 제보 기본
   - guide: `NONE_QUESTION_FRAMES`("어떻게 없애요/예방법/왜") 류를 그대로 guide로
   - none: 중립·영화/노래/회상·애정표현 (기존 none 함정 재활용)
   - 출력: `data/action_data.csv` (컬럼 `text,action`), 클래스 균형 + 누수 방지(test 문장 제외).
   - ⚠ **먼저 50행만 찍어 라벨이 맞는지 눈으로 검증** → 그 다음 전체 생성.
2. **학습** `train_action.py`: `train_to_tflite.py`를 복사해 `DATA_PATH=data/action_data.csv`,
   라벨컬럼 `action`, 출력 파일명을 `models/action_model.tflite` `models/action_vocab.json`
   `models/action_label_map.json`로 변경. 모델 구조(Embedding+GAP)·SEQ_LEN·tokenize는 **그대로**.
3. **추론** `action_predict.py`: `predict.py`의 `load()/predict()` 골격 복사 →
   계약①의 `load_action()` / `predict_action()` 시그니처로 구현. **tokenize는 `from predict import tokenize`** 로 재사용(전처리 일치가 생명).

## DONE 체크 (이게 통과해야 끝)
홀드아웃 5문장 정확도 확인:
```bash
python -c "import action_predict as A; L=A.load_action(); \
fn=lambda t: A.predict_action(t,*L)['action']; \
print(fn('단국대 천안캠퍼스에 말벌집이 생겼어요'), fn('러브버그 너무 많아요'), \
fn('모기 어떻게 없애요?'), fn('오늘 날씨 좋네요'))"
# 기대: emergency dispatch guide none (대체로 맞으면 OK)
```
통과하면 `CONTRACTS.md` STATUS의 `S1` 줄을 `S1 ✅ <위 명령> → emergency dispatch guide none` 로 갱신.
막히면 `S1 ⛔ <사유>`.
