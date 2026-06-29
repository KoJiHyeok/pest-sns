// 해충 제보 — 입력 → /api/predict(진짜 모델) → 결과 렌더
const textEl = document.querySelector("#text");
const resultEl = document.querySelector("#result");

document.querySelectorAll(".ex").forEach((b) => {
  b.addEventListener("click", () => { textEl.value = b.textContent; analyze(); });
});
document.querySelector("#go").addEventListener("click", analyze);
textEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); analyze(); }
});

const RISK_CLASS = { high: "risk-hi", mid: "risk-mid", low: "risk-lo", none: "risk-none" };
const RISK_LABEL = { high: "위험 높음", mid: "위험 중간", low: "위험 낮음", none: "해충 없음" };

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

  const cta = isNone ? "" : `<button class="btn btn-primary" type="button" onclick="location.href='/map'">이 위치에 제보 등록</button>`;

  resultEl.innerHTML = `
    <div class="qblock">
      <div class="qlabel">내가 본 것</div>
      <div class="bubble">${escapeHtml(d.text)}</div>
      <div class="qmeta">AI 분석 완료 · 방금 전</div>
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
    ${prevention}
    ${cta}
  `;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
