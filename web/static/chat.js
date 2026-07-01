// 방역 추천 에이전트 — 프론트(S3). 계약③(POST /chat) 응답 모양만 믿고 UI를 만든다.
// MOCK=true: 실서버 없이 고정 응답으로 UI 완성·확인. S4 연결되면 false 로.
const MOCK = false;  // S4 연결: 실서버(/chat) 사용

const feed = document.getElementById("feed");
const form = document.getElementById("composer");
const field = document.getElementById("field");
const sendBtn = document.getElementById("send");

// ── 계약③ 모양 mock 응답 ───────────────────────────────────────────────
// { reply(\n 포함), pest, action, office:{name,tel} }
function mockReply(message) {
  const t = message.toLowerCase();

  // 1) 말벌 — emergency
  if (/말벌|벌집|벌에\s*쏘|wasp|hornet/.test(t)) {
    return {
      reply:
        "[긴급] 말벌(위험도 高) 발견 상황으로 보여요.\n" +
        "· 즉시: 벌집에 접근하지 말고 자리를 피하세요. 쏘였다면 119에 신고하세요.\n" +
        "· 신고: 말벌집 제거는 소방서(119) 또는 보건소에 연결하세요.",
      pest: "wasp",
      action: "emergency",
      office: { name: "천안시 동남구보건소", tel: "041-521-2691" },
    };
  }

  // 2) 러브버그 — guide(정보·예방)
  if (/러브버그|러브\s*버그|love\s*bug|붉은등우단털파리/.test(t)) {
    return {
      reply:
        "[안내] 러브버그(위험도 低)는 사람을 물지 않고 익충에 가까워요.\n" +
        "· 예방: 밝은 색 옷·강한 빛이 유인하니 외출 시 참고하세요.\n" +
        "· 처리: 물·중성세제 분무로 쉽게 제거되고, 방충망·창틈을 막아두세요.\n" +
        "· 대량 출몰이 계속되면 관할 보건소에 방역을 문의할 수 있어요.",
      pest: "lovebug",
      action: "guide",
      office: { name: "천안시 통합민원실", tel: "041-521-5000" },
    };
  }

  // 3) 잡담 — none
  return {
    reply:
      "해충 관련 내용이 아니에요. 🐝\n" +
      "벌·러브버그·모기·바퀴·진드기·빈대 같은 해충 상황을 알려주시면 도와드릴게요.",
    pest: "none",
    action: "none",
    office: {},
  };
}

// ── 서버/mock 호출 ─────────────────────────────────────────────────────
async function ask(message) {
  if (MOCK) {
    await new Promise((r) => setTimeout(r, 450)); // 응답 느낌
    return mockReply(message);
  }
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

// ── 렌더 ───────────────────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function addUser(text) {
  const row = document.createElement("div");
  row.className = "row row-user";
  const msg = document.createElement("div");
  msg.className = "msg msg-user";
  msg.textContent = text; // textContent → 줄바꿈은 CSS white-space 로 유지
  row.appendChild(msg);
  feed.appendChild(row);
  scrollDown();
}

function addBot(data) {
  const row = document.createElement("div");
  row.className = "row row-bot";
  const msg = document.createElement("div");
  msg.className = "msg msg-bot";

  // reply: \n 유지(esc 후 그대로 — white-space:pre-wrap 이 줄바꿈 렌더)
  let html = esc(data.reply || "");

  // 관공서 전화: tel: 링크 pill
  const office = data.office || {};
  if (office.tel) {
    const dial = String(office.tel).replace(/[^0-9+]/g, "");
    html +=
      `\n<a class="tel-pill" href="tel:${esc(dial)}">` +
      `☎ ${esc(office.name || "전화 연결")} ${esc(office.tel)}</a>`;
  }
  msg.innerHTML = html;
  row.appendChild(msg);
  feed.appendChild(row);
  scrollDown();
}

function addTyping() {
  const row = document.createElement("div");
  row.className = "row row-bot";
  row.id = "typing-row";
  row.innerHTML = '<div class="msg msg-bot"><span class="typing"><span></span><span></span><span></span></span></div>';
  feed.appendChild(row);
  scrollDown();
}
function removeTyping() {
  const t = document.getElementById("typing-row");
  if (t) t.remove();
}

function scrollDown() {
  feed.scrollTop = feed.scrollHeight;
}

// ── 흐름 ───────────────────────────────────────────────────────────────
let busy = false;
async function submit(message) {
  message = (message || "").trim();
  if (!message || busy) return;
  busy = true;
  sendBtn.disabled = true;
  addUser(message);
  field.value = "";
  autoGrow();
  addTyping();
  try {
    const data = await ask(message);
    removeTyping();
    addBot(data);
  } catch (e) {
    removeTyping();
    addBot({ reply: "응답을 받지 못했어요. 잠시 후 다시 시도해 주세요.\n(" + e.message + ")", office: {} });
  } finally {
    busy = false;
    sendBtn.disabled = false;
    field.focus();
  }
}

// 자동 높이
function autoGrow() {
  field.style.height = "auto";
  field.style.height = Math.min(field.scrollHeight, 120) + "px";
}

// ── 이벤트 ─────────────────────────────────────────────────────────────
form.addEventListener("submit", (e) => {
  e.preventDefault();
  submit(field.value);
});

field.addEventListener("input", autoGrow);
field.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submit(field.value);
  }
});

document.getElementById("examples").addEventListener("click", (e) => {
  const btn = e.target.closest(".ex");
  if (btn) submit(btn.textContent);
});

// 첫 인사
addBot({
  reply:
    "안녕하세요! 해충 방역 추천 도우미예요. 🐛\n" +
    "발견한 해충 상황을 알려주시면 어떤 해충인지, 무엇을 해야 할지, 어디에 연락할지 알려드려요.",
  office: {},
});
field.focus();
