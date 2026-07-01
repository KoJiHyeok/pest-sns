# S2 — 도메인: 관공서 데이터 + 추천 결합

너는 방역 추천 에이전트의 **S2(도메인) 세션**이다. `CONTRACTS.md`를 읽고 계약②를 법으로 따른다.
**모델은 필요 없다** — 하드코딩 입력으로 t=0부터 단독 완성한다. 작업 디렉토리: `Hoseo/pest-sns`.

## 목표
`pest + action`을 받아 **대응 가이드 + 관할 관공서 연결**이 담긴 응답 dict를 만드는 순수함수.

## 단계
1. **`offices.json`** (천안 1지역 샘플):
   ```json
   {
     "region": "충남 천안시",
     "보건소":   {"name":"천안시 동남구보건소","tel":"041-...","역할":"방역·해충 민원"},
     "통합민원": {"name":"천안시 콜센터","tel":"120"},
     "긴급":     {"name":"119","역할":"말벌·벌집 제거 출동"}
   }
   ```
   - 전화번호는 **천안시 공식 홈페이지에서 실제값 확인**해 채운다(추측 금지, 못 찾으면 `"확인필요"`).
   - 전국 확장 대비: 지역 키를 늘리기 쉬운 구조로(지금은 천안만).
2. **`recommend.py`**: 계약②의 `recommend(pest, is_real, action, location="")` 구현.
   - `pest_info.json`(읽기)에서 `level·risk·caution·prevention·clothing`을 가져와 `steps` 구성.
   - 결정 로직은 CONTRACTS 2절 표 따름 (none/emergency/dispatch/guide).
   - `reply`는 챗에 그대로 뿌릴 **완성 텍스트**(헤드라인 + · 불릿 + 관공서 ☎). 렌더는 여기 책임.

## DONE 체크
3 시나리오 콘솔 테스트:
```bash
python -c "from recommend import recommend as r; \
print(r('wasp',True,'emergency','천안')['reply']); print('---'); \
print(r('lovebug',True,'guide','')['reply']); print('---'); \
print(r('none',False,'none','')['reply'])"
# 기대: 말벌 긴급(119/보건소) / 러브버그 정보(물뿌리기) / 해충 무관 안내
```
통과하면 STATUS `S2 ✅ <명령> → 3케이스 정상`. 막히면 `S2 ⛔ <사유>`.
