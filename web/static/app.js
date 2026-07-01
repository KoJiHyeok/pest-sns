// 해충 제보 — 입력 → /api/predict(진짜 모델) → 결과 렌더
const textEl = document.querySelector("#text");
const resultEl = document.querySelector("#result");

document.querySelectorAll(".ex").forEach((b) => {
  b.addEventListener("click", () => { textEl.value = b.textContent; analyze(); });
});
document.querySelector("#go").addEventListener("click", analyze);
textEl.addEventListener("keydown", (e) => {
  // Enter = 분석, Shift+Enter = 줄바꿈(기본 동작 유지).
  // e.isComposing(keyCode 229): 한글 IME 조합 중 Enter(글자 확정)는 제출하지 않는다.
  if (e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  analyze();
});

const RISK_CLASS = { high: "risk-hi", mid: "risk-mid", low: "risk-lo", none: "risk-none" };
const RISK_LABEL = { high: "위험 높음", mid: "위험 중간", low: "위험 낮음", none: "해충 없음" };
let lastResult = null;

async function analyze() {
  const text = textEl.value.trim();
  if (!text) { textEl.focus(); return; }
  resultEl.innerHTML = '<div class="loading">분석 중…</div>';
  try {
    const res = await fetch("/api/predict", {
      method: "POST",
      headers: {
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
      },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "서버 오류");
    render(data);
  } catch (err) {
    resultEl.innerHTML = `<div class="loading">에러: ${escapeHtml(err.message)}</div>`;
  }
}

function render(d) {
  lastResult = d;
  const conf = Math.round(d.confidence * 100);
  const info = d.info || {};
  const level = info.level || "none";
  const isNone = d.pest_en === "none";

  const cands = d.probs.slice(0, 3).map((c, i) => {
    const pct = Math.round(c.p * 100);
    const fill = i === 0 ? "#1E6B57" : "#C7D2CC";
    return `<div class="crow"><span class="cname">${escapeHtml(c.kr)}</span>`
      + `<span class="ctrack"><span class="cfill" style="width:${pct}%; background:${fill};"></span></span>`
      + `<span class="cpct">${pct}%</span></div>`;
  }).join("");

  let prevention = "";
  if (!isNone && info.title) {
    const rows = [["위험도", "risk"], ["권장 의류", "clothing"], ["예방법", "prevention"],
                 ["주의사항", "caution"], ["기피성분", "repellent"]];
    const filled = rows.filter(([, k]) => info[k]);
    const body = filled.map(([label, k], idx) => {
      const last = idx === filled.length - 1 ? " prow-last" : "";
      const rcls = k === "risk" ? " pv-risk" : "";
      return `<div class="prow${last}"><span class="pk">${label}</span>`
        + `<span class="pv${rcls}">${escapeHtml(info[k])}</span></div>`;
    }).join("");
    const src = info.source || "research/새 텍스트 문서.md";
    prevention = `<div class="pcard"><div class="phead"><span class="pdot pdot-${level}"></span>예방 가이드</div>`
      + `${body}<div class="src">출처: ${escapeHtml(src)}</div></div>`;
  } else if (isNone) {
    prevention = `<div class="okcard">해충 신호가 감지되지 않았습니다.</div>`;
  }

  // ── 방역 도우미 카드 (action + 관할 보건소 + 지역) ──────────────────────
  let advisoryCard = "";
  if (d.advisory && !isNone) {
    const a = d.advisory;
    const ACT = { emergency: "긴급 대응", dispatch: "방역 신고", guide: "예방 안내", none: "안내" };
    const BADGE = { emergency: "#C0392B", dispatch: "#1E6B57", guide: "#5B7A8C", none: "#5B7A8C" };
    const actLabel = ACT[a.action] || "안내";
    const badge = BADGE[a.action] || "#5B7A8C";
    const rg = a.region || {};
    const regionTxt = rg.sigungu
      ? escapeHtml(`${rg.sido || ""} ${rg.sigungu}`.trim())
      : '<span style="color:#8a6d3b;">지역 미지정</span>';
    const o = a.office || {};
    let officeHtml;
    if (o.tel) {
      const dial = String(o.tel).replace(/[^0-9+]/g, "");
      officeHtml = `<a href="tel:${escapeHtml(dial)}" style="display:inline-block;margin-top:4px;padding:8px 12px;background:#1E6B57;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">☎ ${escapeHtml(o.name || "관할 보건소")} ${escapeHtml(o.tel)}</a>`;
    } else {
      officeHtml = `<div style="margin-top:4px;color:#8a6d3b;">지역(시/군/구)을 알려주시면 관할 보건소 연락처를 안내해 드려요.</div>`;
    }
    advisoryCard = `<div class="pcard">`
      + `<div class="phead"><span style="display:inline-block;padding:2px 8px;border-radius:6px;background:${badge};color:#fff;font-size:12px;margin-right:6px;">${actLabel}</span>방역 도우미</div>`
      + `<div class="prow"><span class="pk">관할 보건소</span><span class="pv">${regionTxt}</span></div>`
      + `<div style="padding:2px 14px 12px;">${officeHtml}</div></div>`;
  }

  const locHint = d.location_guess ? `<div class="qmeta">위치 후보 · ${escapeHtml(d.location_guess)}</div>` : "";
  const cta = isNone ? "" : `<button id="register-report" class="btn btn-primary" type="button">이 위치에 제보 등록</button>`;

  resultEl.innerHTML = `
    <div class="qblock">
      <div class="qlabel">내가 본 것</div>
      <div class="bubble">${escapeHtml(d.text)}</div>
      <div class="qmeta">AI 분석 완료 · 방금 전</div>
      ${locHint}
    </div>
    <div class="card">
      <div class="reshead">
        <div>
          <div class="reslabel">판별 결과</div>
          <div class="pest">${escapeHtml(d.pest_kr)}</div>
          <div class="pesten">${escapeHtml(d.pest_en)}</div>
        </div>
        <div class="risk ${RISK_CLASS[level]}">${RISK_LABEL[level]}</div>
      </div>
      <div class="conf">
        <div class="confrow"><span class="conflab">확신도</span><span class="confval">${conf}%</span></div>
        <div class="bar"><div class="barfill" style="width:${conf}%;"></div></div>
      </div>
      <div class="cands">${cands}</div>
    </div>
    ${advisoryCard}
    ${prevention}
    ${cta}
  `;
  const registerBtn = document.querySelector("#register-report");
  if (registerBtn) registerBtn.addEventListener("click", registerReport);
}

async function registerReport() {
  if (!lastResult) return;
  const btn = document.querySelector("#register-report");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "위치 검색 중";
  }
  try {
    const res = await fetch("/api/reports", {
      method: "POST",
      headers: {
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
      },
      body: JSON.stringify({
        text: lastResult.text,
        pest_en: lastResult.pest_en,
        location: lastResult.location_guess || "",
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "등록 실패");
    const loc = data.report && data.report.location ? data.report.location : "";
    location.href = `/map?loc=${encodeURIComponent(loc)}`;
  } catch (err) {
    resultEl.insertAdjacentHTML("beforeend", `<div class="loading">에러: ${escapeHtml(err.message)}</div>`);
    if (btn) {
      btn.disabled = false;
      btn.textContent = "이 위치에 제보 등록";
    }
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
