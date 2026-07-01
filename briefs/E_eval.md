# E — action 모델 eval 하니스

너는 방역 추천 에이전트 **Phase2 E(평가) 세션**이다. `CONTRACTS.md`를 읽고, 네 소유 파일만 쓴다.
작업 디렉토리: `Hoseo/pest-sns`. **완전 독립** — 아무도 안 기다린다.

## 목표
새 action 모델을 "느낌"이 아니라 **숫자**로 검증. 기존 pest의 `eval_holdout.py` 스타일을 참고하되 action용으로.

## 소유 파일 (이것만)
`eval_action.py`

## 단계
1. `data/action_data.csv`(S1 생성, 컬럼 `text,action`)에서 **홀드아웃** 분리.
   - ⚠ 학습과 동일 시드/전처리 가정 금지 — `train_action.py`가 어떻게 split하는지 읽고 **겹치지 않는** 평가셋 확보. 누수 있으면 점수가 거짓이 된다(테스트셋=학습셋 교집합 0을 assert).
2. `action_predict.predict_action`으로 홀드아웃 추론 → 출력:
   - 전체 정확도(accuracy)
   - **클래스별** precision/recall (emergency·dispatch·guide·none)
   - **혼동행렬**(어떤 action이 어떤 action으로 헷갈리는지)
3. 추가: chat_app의 **이음새 케이스**도 따로 점검 — guide 질문("모기 어떻게 없애요?")이 action에서 guide로 잘 가는지, none과 얼마나 헷갈리는지 표로.

## 왜 중요 (맥락)
이 숫자가 있어야 "키워드 복구 band-aid가 실제로 몇 %를 메우나", "이음새가 얼마나 새나"를 객관화하고
다음 작업(단일모델 통합 vs 라벨정렬, 신뢰도 임계)을 **추측이 아니라 데이터로** 정한다.

## DONE 체크
```bash
../.venv/Scripts/python.exe eval_action.py
# 기대: accuracy + 클래스별 지표 + 혼동행렬 출력. 누수 assert 통과.
```
통과하면 STATUS `E ✅ accuracy=0.XX, 혼동행렬 출력. 약점: <한 줄>`. 막히면 `E ⛔ <사유>`.
