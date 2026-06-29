// 지도 페이지 — Kakao Map JS 키 → 실제 지도 + 제보 마커 + 필터.
// 필터(오늘/해충 드롭다운/위험높음만)는 전부 클라이언트에서 처리 → 서버 재시작 불필요.
// 배포 환경에서는 서버가 window.KAKAO_JS_KEY 를 주입하고, 로컬 수동 입력은 localStorage 에 저장한다.
const COLOR = { high: "#C0352B", mid: "#C77D27", low: "#2E7D5B" };
const RISK_CLASS = { high: "risk-hi", mid: "risk-mid", low: "risk-lo" };
const RISK_LABEL = { high: "위험 높음", mid: "위험 중간", low: "위험 낮음" };
const RANK = { low: 1, mid: 2, high: 3 };

// 해충 메타(none 제외): 한글명·위험등급·예방 한 줄. 드롭다운 순서이기도 함.
const META = {
  mosquito:  { kr: "모기",     level: "mid",  hint: "밝은 긴 옷·고인 물 제거·기피제(DEET·이카리딘)." },
  lovebug:   { kr: "러브버그",  level: "low",  hint: "어두운 옷 권장·야간 조명 최소화·물 분사." },
  wasp:      { kr: "말벌",     level: "high", hint: "밝은 옷·향수 자제·벌집 20m 대피·쏘이면 119." },
  tick:      { kr: "진드기",    level: "high", hint: "밝은 긴 옷·풀숲 회피·귀가 후 즉시 세탁/샤워." },
  cockroach: { kr: "바퀴벌레",  level: "mid",  hint: "위생 관리·배설물 접촉 주의·살충제 오남용 주의." },
  bedbug:    { kr: "빈대",     level: "low",  hint: "중고가구 점검·60℃ 고온 세탁·스팀(70~90℃) 처리." },
};
const PEST_KEYS = Object.keys(META);

const LS_KEY = "kakao_js_key";
const keyInput = document.querySelector("#keyinput");
const keybar = document.querySelector("#keybar");
const keyhint = document.querySelector("#keyhint");
const keyreset = document.querySelector("#keyreset");
const placeholder = document.querySelector("#placeholder");
const mapDiv = document.querySelector("#kakaomap");
const CONFIGURED_KAKAO_JS_KEY = String(window.KAKAO_JS_KEY || "").trim();

// 필터 칩 — map.html 순서: [오늘] [전체 해충] [위험 높음만]
const chips = document.querySelectorAll(".chips .chip");
const cToday = chips[0], cPest = chips[1], cRisk = chips[2];
const head = document.querySelector(".head");
const state = { today: false, pest: null, highOnly: false };

let RAW = [], GEO = {}, MARKERS = [], MAP = null, overlays = [], ddMenu = null;

// ---- 키 / SDK ----
document.querySelector("#keyapply").addEventListener("click", apply);
keyInput.addEventListener("keydown", (e) => { if (e.key === "Enter") apply(); });
keyreset.addEventListener("click", () => { localStorage.removeItem(LS_KEY); location.reload(); });

if (CONFIGURED_KAKAO_JS_KEY) {
  keybar.style.display = "none";
  keyhint.style.display = "none";
  keyreset.style.display = "none";
  loadSdk(CONFIGURED_KAKAO_JS_KEY);
} else {
  const saved = localStorage.getItem(LS_KEY);
  if (saved) { keyInput.value = saved; loadSdk(saved); }
}

function apply() {
  const key = keyInput.value.trim();
  if (!key) { keyInput.focus(); return; }
  localStorage.setItem(LS_KEY, key);
  loadSdk(key);
}
function loadSdk(key) {
  if (window.kakao && window.kakao.maps) { initMap(); return; }
  const s = document.createElement("script");
  s.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`;
  s.onload = () => window.kakao.maps.load(initMap);
  s.onerror = () => alert("Kakao 지도 SDK 로드 실패 — 키/도메인 등록/카카오맵 서비스 활성화를 확인하세요.");
  document.head.appendChild(s);
}

// ---- 필터 칩 ----
if (cToday) cToday.addEventListener("click", () => { state.today = !state.today; syncChips(); render(); });
if (cRisk) cRisk.addEventListener("click", () => { state.highOnly = !state.highOnly; syncChips(); render(); });
if (cPest) cPest.addEventListener("click", (e) => { e.stopPropagation(); toggleDropdown(); });
document.addEventListener("click", () => closeDropdown());
syncChips();

function syncChips() {
  if (cToday) cToday.className = "chip" + (state.today ? " chip-on" : "");
  if (cRisk) cRisk.className = "chip" + (state.highOnly ? " chip-on" : "");
  if (cPest) {
    cPest.textContent = (state.pest ? META[state.pest].kr : "전체 해충") + " ▾";
    cPest.className = "chip chip-dd" + (state.pest ? " chip-on" : "");
  }
}

// ---- 해충 드롭다운 ----
function pestCounts() {
  const c = {};
  if (RAW.length) {
    RAW.forEach((r) => { if (r.pest_label !== "none") c[r.pest_label] = (c[r.pest_label] || 0) + 1; });
  } else {
    MARKERS.forEach((r) => { if (r.pest_en) c[r.pest_en] = (c[r.pest_en] || 0) + (r.count || 0); });
  }
  return c;
}

function toggleDropdown() {
  if (ddMenu && ddMenu.classList.contains("open")) { closeDropdown(); return; }
  openDropdown();
}

function openDropdown() {
  const counts = pestCounts();
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (!ddMenu) { ddMenu = document.createElement("div"); ddMenu.className = "ddmenu"; head.appendChild(ddMenu); }

  const rows = [{ key: null, kr: "전체 해충", color: "#1E6B57", n: total }]
    .concat(PEST_KEYS.map((k) => ({ key: k, kr: META[k].kr, color: COLOR[META[k].level], n: counts[k] || 0 })));

  ddMenu.innerHTML = rows.map((r) => {
    const sel = (r.key === state.pest) ? " sel" : "";
    return `<div class="dditem${sel}" data-key="${r.key === null ? "" : r.key}">`
      + `<span class="dddot" style="background:${r.color};"></span>`
      + `<span class="ddname">${r.kr}</span><span class="ddn">${r.n}</span></div>`;
  }).join("");

  ddMenu.querySelectorAll(".dditem").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const k = el.getAttribute("data-key");
      state.pest = k || null;
      closeDropdown();
      syncChips();
      render();
    });
  });

  // 칩 바로 아래에 위치 (.head 기준 offset)
  ddMenu.style.left = cPest.offsetLeft + "px";
  ddMenu.style.top = (cPest.offsetTop + cPest.offsetHeight + 6) + "px";
  ddMenu.classList.add("open");
}

function closeDropdown() { if (ddMenu) ddMenu.classList.remove("open"); }

// ---- 지도 ----
async function initMap() {
  placeholder.style.display = "none";
  keybar.style.display = "none";
  keyhint.style.display = "none";
  keyreset.style.display = CONFIGURED_KAKAO_JS_KEY ? "none" : "";
  mapDiv.style.display = "block";
  MAP = new kakao.maps.Map(mapDiv, { center: new kakao.maps.LatLng(37.45, 127.0), level: 9 });

  try {
    const [rep, geo] = await Promise.all([
      fetchJson("/static/reports.json"),
      fetchJson("/static/geocode.json"),
    ]);
    RAW = rep; GEO = geo;
  } catch (e) {
    console.warn("정적 제보 데이터 로드 실패, API 집계 데이터로 대체합니다.", e);
    try {
      MARKERS = await fetchJson("/api/reports");
    } catch (apiErr) {
      console.error("제보 데이터 로드 실패", apiErr);
    }
  }
  render();
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} ${res.status}`);
  return res.json();
}

function aggregate() {
  if (!RAW.length) {
    let out = MARKERS.slice();
    if (state.today) out = out.filter((r) => r.recent < 1440);
    if (state.pest) out = out.filter((r) => r.pest_en === state.pest);
    if (state.highOnly) out = out.filter((r) => r.level === "high");
    out.sort((a, b) => b.count - a.count);
    return out;
  }

  let rs = RAW.filter((r) => r.pest_label !== "none");
  if (state.today) rs = rs.filter((r) => r.minutes_ago < 1440);
  if (state.pest) rs = rs.filter((r) => r.pest_label === state.pest);

  const byLoc = {};
  rs.forEach((r) => { (byLoc[r.location] = byLoc[r.location] || []).push(r); });

  let out = [];
  Object.keys(byLoc).forEach((loc) => {
    const coord = GEO[loc];
    if (!coord) return;
    const items = byLoc[loc];
    const counts = {};
    items.forEach((r) => { counts[r.pest_label] = (counts[r.pest_label] || 0) + 1; });
    const headline = Object.keys(counts).sort(
      (a, b) => counts[b] - counts[a] || RANK[META[b].level] - RANK[META[a].level]
    )[0];
    const m = META[headline];
    out.push({
      location: loc, lat: coord.lat, lng: coord.lng, count: items.length,
      pest_en: headline, pest_kr: m.kr, level: m.level, hint: m.hint,
      recent: Math.min.apply(null, items.map((r) => r.minutes_ago)),
    });
  });
  if (state.highOnly) out = out.filter((o) => o.level === "high");
  out.sort((a, b) => b.count - a.count);
  return out;
}

function render() {
  if (!MAP) return;
  overlays.forEach((o) => o.setMap(null));
  overlays = [];

  const data = aggregate();
  if (!data.length) {
    setSheet("결과 없음", "이 조건에 맞는 제보가 없어요", "risk-none", "—", "필터를 바꿔보세요.");
    document.querySelector("#reportlist").innerHTML = "";
    return;
  }

  const bounds = new kakao.maps.LatLngBounds();
  data.forEach((r) => {
    const pos = new kakao.maps.LatLng(r.lat, r.lng);
    bounds.extend(pos);
    const el = document.createElement("div");
    el.className = "kmk";
    el.style.background = COLOR[r.level] || "#888";
    el.textContent = r.count;
    el.title = `${r.location} · ${r.pest_kr} (${r.count}건)`;
    el.addEventListener("click", () => select(r));
    overlays.push(new kakao.maps.CustomOverlay({ map: MAP, position: pos, content: el, xAnchor: 0.5, yAnchor: 0.5 }));
  });
  MAP.setBounds(bounds);
  select(data[0]);
  renderList(data.slice(1, 6));
}

function select(r) {
  setSheet(r.location, `${r.pest_kr} · 제보 ${r.count}건 · 가장 최근 ${ago(r.recent)}`,
           RISK_CLASS[r.level] || "risk-none", RISK_LABEL[r.level] || "정보 없음", r.hint || "");
  if (MAP) MAP.panTo(new kakao.maps.LatLng(r.lat, r.lng));
}

function setSheet(name, meta, riskCls, riskLabel, hint) {
  document.querySelector("#selname").textContent = name;
  document.querySelector("#selmeta").textContent = meta;
  const rk = document.querySelector("#selrisk");
  rk.className = `risk ${riskCls}`;
  rk.textContent = riskLabel;
  document.querySelector("#selhint").textContent = hint;
}

function renderList(items) {
  document.querySelector("#reportlist").innerHTML = items.map((r, i) => {
    const last = i === items.length - 1 ? " li-last" : "";
    return `<div class="li${last}"><span class="lidot" style="background:${COLOR[r.level] || "#888"};"></span>`
      + `<span class="lic"><span class="lit">${esc(r.location)} · ${esc(r.pest_kr)}</span>`
      + `<span class="lis">제보 ${r.count}건 · ${RISK_LABEL[r.level] || ""}</span></span>`
      + `<span class="litime">${ago(r.recent)}</span></div>`;
  }).join("");
}

function ago(m) {
  if (m == null) return "";
  if (m < 60) return `${m}분 전`;
  if (m < 1440) return `${Math.floor(m / 60)}시간 전`;
  return `${Math.floor(m / 1440)}일 전`;
}
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
