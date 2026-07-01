// 지도 페이지 — Kakao Map JS 키 → 실제 지도 + 제보 마커 + 필터.
// 필터(오늘/해충 드롭다운/위험높음만)는 전부 클라이언트에서 처리 → 서버 재시작 불필요.
// 배포 환경에서는 서버가 window.KAKAO_JS_KEY 를 주입하고, 로컬 수동 입력은 localStorage 에 저장한다.
//
// 클러스터링: Kakao 기본 MarkerClusterer 는 클러스터 색을 '개수'로만 칠해 위험도와 색 의미가
// 꼬인다. 그래서 직접 만든 '격자 클러스터링'을 쓴다 → 묶음 색 = 그 안의 '최고 위험도' 색으로
// 칠해 "빨간 구역 = 위험지역"이 한눈에 보이게(범례·개별 핀과 색 의미 일치).
const COLOR = { high: "#C0352B", mid: "#C77D27", low: "#2E7D5B" };
const RISK_CLASS = { high: "risk-hi", mid: "risk-mid", low: "risk-lo" };
const RISK_LABEL = { high: "위험 높음", mid: "위험 중간", low: "위험 낮음" };
const RANK = { low: 1, mid: 2, high: 3 };
const RANK_OF = { low: 0, mid: 1, high: 2 };

// 격자 한 칸의 위도/경도 크기(도). 줌아웃(Kakao level↑)일수록 크게 묶는다.
// 값을 키우면 더 적극적으로 묶이고, 줄이면 더 잘게 쪼개진다(튜닝 노브).
const CELL_BASE = 0.00018;
function cellDegForLevel(level) { return CELL_BASE * Math.pow(2, level); }

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
const URL_PARAMS = new URLSearchParams(location.search);
const FOCUS_LOC = normalizeLoc(URL_PARAMS.get("loc") || "");
const FOCUS_ZOOM = 3;      // 제보 직후 그 장소를 확대할 Kakao 줌 레벨(작을수록 더 확대)
let focusHandled = false;  // ?loc= 확대는 도착 첫 렌더에 한 번만

// 필터 칩 — map.html 순서: [오늘] [전체 해충] [위험 높음만]
const chips = document.querySelectorAll(".chips .chip");
const cToday = chips[0], cPest = chips[1], cRisk = chips[2];
const head = document.querySelector(".head");
const state = { today: false, pest: null, highOnly: false };

let RAW = [], GEO = {}, MARKERS = [], MAP = null, ddMenu = null;
let DATA = [], OVERLAYS = [], idleBound = false;

// ---- 제보 시트(바텀시트) 접기/펼치기 ----
// 디폴트 = 일부 내려간(접힌) 상태로, 회색 바(.grip)를 눌러 펼치고/접는다.
// translateY 로 시트를 아래로 밀어 핸들+선택지역 요약(selrow)만 남기고 나머지는 화면 밖으로
// (.screen overflow:hidden 으로 잘림). 콘텐츠 높이가 가변이라 오프셋은 그때그때 측정한다.
const sheet = document.querySelector("#sheet");
const sheetGrip = document.querySelector("#sheetGrip");
let sheetCollapsed = true;

function sheetPeekHeight() {
  const selrow = sheet.querySelector(".selrow");
  if (!selrow) return 64;
  return selrow.offsetTop + selrow.offsetHeight + 12; // 핸들 + 선택지역 요약까지 보이게
}
function sheetMaxOffset() { return Math.max(0, sheet.offsetHeight - sheetPeekHeight()); }
function applySheet() {
  if (!sheet) return;
  sheet.style.transform = `translateY(${sheetCollapsed ? sheetMaxOffset() : 0}px)`;
}

// 회색 바: 클릭(탭)이면 토글, 끌면 손가락/마우스 따라 위·아래로 움직이고 놓으면 가까운 쪽으로 스냅.
let dragging = false, dragStartY = 0, dragStartOffset = 0, dragMax = 0, dragMoved = 0;

function curOffset() {
  const m = /translateY\(([-0-9.]+)px\)/.exec(sheet.style.transform || "");
  return m ? parseFloat(m[1]) : (sheetCollapsed ? sheetMaxOffset() : 0);
}
function onGripDown(e) {
  dragging = true;
  dragMoved = 0;
  dragStartY = e.clientY;
  dragMax = sheetMaxOffset();
  dragStartOffset = curOffset();
  sheet.style.transition = "none";        // 드래그 중엔 즉시 따라오게
  if (sheetGrip.setPointerCapture) sheetGrip.setPointerCapture(e.pointerId);
  e.preventDefault();
}
function onGripMove(e) {
  if (!dragging) return;
  const dy = e.clientY - dragStartY;       // 아래로 끌면 +(접힘 방향), 위로 끌면 −(펼침)
  dragMoved = Math.max(dragMoved, Math.abs(dy));
  const off = Math.min(dragMax, Math.max(0, dragStartOffset + dy));
  sheet.style.transform = `translateY(${off}px)`;
}
function onGripUp() {
  if (!dragging) return;
  dragging = false;
  sheet.style.transition = "";             // 스냅 애니메이션 복구
  if (dragMoved < 6) {
    sheetCollapsed = !sheetCollapsed;        // 사실상 탭 → 토글
  } else {
    sheetCollapsed = curOffset() > dragMax / 2;  // 절반 넘게 내려갔으면 접힘
  }
  applySheet();
}
if (sheetGrip) {
  sheetGrip.addEventListener("pointerdown", onGripDown);
  window.addEventListener("pointermove", onGripMove);
  window.addEventListener("pointerup", onGripUp);
}
// 폰트 로드 후 높이가 바뀔 수 있어 첫 레이아웃 다음 프레임에 한 번 더 맞춘다.
requestAnimationFrame(applySheet);
window.addEventListener("load", applySheet);

// ---- 장소 검색 (kakao.maps.services.Places) ----
const searchBar = document.querySelector("#searchbar");
const searchInput = document.querySelector("#placeinput");
const searchBtn = document.querySelector("#placesearch");
const searchMsg = document.querySelector("#searchmsg");
let searchMarker = null;

function showSearchMsg(t) { if (searchMsg) { searchMsg.textContent = t; searchMsg.style.display = "block"; } }
function hideSearchMsg() { if (searchMsg) searchMsg.style.display = "none"; }

function placeSearchMarker(pos, label) {
  if (searchMarker) searchMarker.setMap(null);
  const el = document.createElement("div");
  el.className = "searchpin";
  el.textContent = "📍";
  el.title = label || "";
  searchMarker = new kakao.maps.CustomOverlay({ map: MAP, position: pos, content: el, xAnchor: 0.5, yAnchor: 1, zIndex: 5 });
}

function doSearch() {
  const q = (searchInput.value || "").trim();
  if (!q || !MAP) return;
  if (!(window.kakao && kakao.maps.services)) { showSearchMsg("검색 서비스를 불러오지 못했어요."); return; }
  const ps = new kakao.maps.services.Places();
  ps.keywordSearch(q, (data, status) => {
    if (status === kakao.maps.services.Status.OK && data.length) {
      const p = data[0];
      const pos = new kakao.maps.LatLng(p.y, p.x);
      MAP.setLevel(4);
      MAP.setCenter(pos);
      placeSearchMarker(pos, p.place_name);
      hideSearchMsg();
    } else {
      showSearchMsg(`‘${q}’ 검색 결과가 없어요.`);
    }
  });
}
if (searchBtn) searchBtn.addEventListener("click", doSearch);
if (searchInput) searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); doSearch(); }
});

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
  // libraries=services → 장소 검색(kakao.maps.services.Places) 사용
  s.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false&libraries=services`;
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
  if (searchBar) searchBar.style.display = "flex";   // 지도 활성화 후에만 장소 검색 노출
  mapDiv.style.display = "block";
  MAP = new kakao.maps.Map(mapDiv, { center: new kakao.maps.LatLng(37.45, 127.0), level: 9 });

  try {
    const dynamic = await fetchJson("/api/reports/raw");
    RAW = dynamic.reports || [];
    GEO = dynamic.geocode || {};
  } catch (e) {
    console.warn("동적 제보 데이터 로드 실패, 정적 데이터로 대체합니다.", e);
    try {
      const [rep, geo] = await Promise.all([
        fetchJson("/static/reports.json"),
        fetchJson("/static/geocode.json"),
      ]);
      RAW = rep; GEO = geo;
    } catch (staticErr) {
      console.warn("정적 제보 데이터 로드 실패, API 집계 데이터로 대체합니다.", staticErr);
      try {
        MARKERS = await fetchJson("/api/reports");
      } catch (apiErr) {
        console.error("제보 데이터 로드 실패", apiErr);
      }
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

// ---- 격자 클러스터링 (색 = 묶음 안 최고 위험도) ----
function clearOverlays() {
  OVERLAYS.forEach((o) => o.setMap(null));
  OVERLAYS = [];
}

function maxRiskLevel(items) {
  return items.reduce((acc, r) => (RANK_OF[r.level] > RANK_OF[acc] ? r.level : acc), "low");
}

function drawClusters() {
  if (!MAP) return;
  clearOverlays();
  if (!DATA.length) return;

  const cell = cellDegForLevel(MAP.getLevel());
  const cells = {};
  DATA.forEach((r) => {
    const key = Math.floor(r.lat / cell) + ":" + Math.floor(r.lng / cell);
    (cells[key] = cells[key] || []).push(r);
  });

  Object.values(cells).forEach((items) => {
    const lat = items.reduce((s, r) => s + r.lat, 0) / items.length;
    const lng = items.reduce((s, r) => s + r.lng, 0) / items.length;
    const pos = new kakao.maps.LatLng(lat, lng);
    const el = document.createElement("div");

    if (items.length === 1) {
      // 단일 지점 핀 — 위험도 색 + 제보 수
      const r = items[0];
      el.className = "kmk";
      el.style.background = COLOR[r.level] || "#888";
      el.textContent = r.count;
      el.title = `${r.location} · ${r.pest_kr} (${r.count}건)`;
      el.addEventListener("click", () => select(r));
      OVERLAYS.push(new kakao.maps.CustomOverlay({ map: MAP, position: pos, content: el, xAnchor: 0.5, yAnchor: 0.5, zIndex: 1 }));
    } else {
      // 클러스터 — 색은 '묶음 안 최고 위험도', 크기는 총 제보 수
      const total = items.reduce((s, r) => s + r.count, 0);
      const lvl = maxRiskLevel(items);
      const size = total >= 30 ? 54 : total >= 10 ? 46 : 38;
      el.className = "kmc kmc-" + lvl;
      el.style.background = COLOR[lvl] || "#888";
      el.style.width = el.style.height = size + "px";
      el.style.fontSize = (total >= 30 ? 15 : total >= 10 ? 14 : 13) + "px";
      el.textContent = total;
      el.title = `${items.length}곳 · 제보 ${total}건 · 최고 위험: ${RISK_LABEL[lvl]}`;
      el.addEventListener("click", () => {
        MAP.setLevel(Math.max(1, MAP.getLevel() - 2), { anchor: pos });
      });
      OVERLAYS.push(new kakao.maps.CustomOverlay({ map: MAP, position: pos, content: el, xAnchor: 0.5, yAnchor: 0.5, zIndex: 2 }));
    }
  });
}

function render() {
  if (!MAP) return;
  DATA = aggregate();
  if (!DATA.length) {
    clearOverlays();
    setSheet("결과 없음", "이 조건에 맞는 제보가 없어요", "risk-none", "—", "필터를 바꿔보세요.");
    document.querySelector("#reportlist").innerHTML = "";
    return;
  }

  // 줌/이동할 때마다 다시 묶기 (리스너는 한 번만 바인딩)
  if (!idleBound) {
    kakao.maps.event.addListener(MAP, "idle", drawClusters);
    idleBound = true;
  }

  // 제보 직후 ?loc= 로 넘어온 경우에만(첫 렌더 1회) 그 장소를 확대해서 정확히 보여준다.
  // 이후 필터를 바꿔도 다시 튕기지 않게 focusHandled 로 한 번만 적용한다.
  const focused = (FOCUS_LOC && !focusHandled)
    ? DATA.find((r) => normalizeLoc(r.location) === FOCUS_LOC) : null;
  if (focused) {
    focusHandled = true;
    MAP.setLevel(FOCUS_ZOOM);
    MAP.setCenter(new kakao.maps.LatLng(focused.lat, focused.lng));
    sheetCollapsed = false; applySheet();   // 그 장소 정보가 바로 보이게 시트 펼침
  } else {
    const bounds = new kakao.maps.LatLngBounds();
    DATA.forEach((r) => bounds.extend(new kakao.maps.LatLng(r.lat, r.lng)));
    MAP.setBounds(bounds);   // 이동 후 idle → drawClusters 자동 호출
  }
  drawClusters();            // 이동이 없을 때도 즉시 한 번 그린다

  const selected = focused || DATA[0];
  select(selected);
  renderList(DATA.filter((r) => r !== selected).slice(0, 5));
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
  applySheet();   // 내용(높이) 바뀌면 접힘 오프셋 재계산
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
function normalizeLoc(s) {
  return String(s || "").replace(/\s+/g, "");
}
