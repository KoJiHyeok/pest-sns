# S3 — 프론트: 독립 챗 웹페이지

너는 방역 추천 에이전트의 **S3(프론트) 세션**이다. `CONTRACTS.md`를 읽고 계약③(챗 API 모양)을 법으로 따른다.
**백엔드를 안 기다린다** — mock으로 t=0부터 UI를 완성한다. 작업 디렉토리: `Hoseo/pest-sns`.

## 목표
해충 상황을 입력하면 추천 응답이 말풍선으로 뜨는 **독립 챗 페이지**. 가볍고 데모하기 좋게.

## 소유 파일 (이 3개만)
`web/static/chat.html` · `web/static/chat.js` · `web/static/chat.css`

## 요구사항
- 채팅 UI: 입력창 + 전송, 사용자/봇 말풍선, 스크롤. 모바일 폭에서도 보기 좋게.
- `chat.js`: 사용자가 보내면 `POST /chat {"message": ...}` → 응답의 `reply`(줄바꿈 `\n` 유지)를 봇 말풍선에 렌더. `office.tel` 있으면 `tel:` 링크로.
- **mock 토글**: `chat.js` 최상단 `const MOCK = true;`
  - `true`: `/chat` 호출 대신 계약③ 모양 고정 응답을 반환(예: 말벌 emergency 케이스)으로 UI 완성·확인.
  - S4 연결되면 `false`로 바꾸면 실서버 사용.
- 예시 대화 3개(말벌 긴급 / 러브버그 정보 / 잡담)가 mock에서 자연스럽게 보이도록.

## DONE 체크
브라우저로 `web/static/chat.html` 직접 열기(MOCK=true) → 메시지 보내면 말풍선 응답이 뜨고
줄바꿈/관공서 전화 링크가 정상 렌더. 통과하면 STATUS `S3 ✅ chat.html MOCK 렌더 정상`.
막히면 `S3 ⛔ <사유>`.
