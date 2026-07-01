// 지도 페이지 — MapLibre GL + CARTO Dark 타일 → 다크 "제보 관제" 지도.
// 엔진은 MapLibre(무료·키 불필요), 타일은 CARTO dark_all(무료, OSM 기반).
// 집계·필터·드롭다운·시트 로직은 Kakao 시절 그대로 재사용한다(지도 그리는 부분만 교체).
// ⚠️ 좌표 순서: MapLibre 는 [lng, lat] (GeoJSON 순서). Kakao 의 (lat, lng) 와 반대다.
const COLOR = { high: "#FF5B52", mid: "#FFB13C", low: "#27D3A6" };
const RISK_CLASS = { high: "risk-hi", mid: "risk-mid", low: "risk-lo" };
const RISK_LABEL = { high: "위험 높음", mid: "위험 중간", low: "위험 낮음" };
const RANK = { low: 1, mid: 2, high: 3 };

// CARTO Dark Matter 래스터 타일 (무료·키 불필요, 저작자 표시 필수).
const DARK_STYLE = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [{ id: "carto", type: "raster", source: "carto" }],
};

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

const placeholder = document.querySelector("#placeholder");
const mapDiv = document.querySelector("#kakaomap");
const URL_PARAMS = new URLSearchParams(location.search);
const FOCUS_LOC = normalizeLoc(URL_PARAMS.get("loc") || "");

// 필터 칩 — map.html 순서: [오늘] [전체 해충] [위험 높음만]
const chips = document.querySelectorAll(".chips .chip");
const cToday = chips[0], cPest = chips[1], cRisk = chips[2];
const head = document.querySelector(".head");
const state = { today: false, pest: null, highOnly: false };

let RAW = [], GEO = {}, MARKERS = [], MAP = null, overlays = [], ddMenu = null;

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

  const rows = [{ key: null, kr: "전체 해충", color: "#9AE6D0", n: total }]
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

// ---- 지도 (MapLibre) ----
async function initMap() {
  if (placeholder) placeholder.style.display = "none";
  mapDiv.style.display = "block";

  MAP = new maplibregl.Map({
    container: mapDiv,
    style: DARK_STYLE,
    center: [127.0, 37.45],   // [lng, lat]
    zoom: 6.2,
    attributionControl: { compact: true },
  });
  MAP.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
  await new Promise((res) => MAP.on("load", res));

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

function makeMarkerEl(r) {
  const color = COLOR[r.level] || "#888";
  const el = document.createElement("div");
  el.className = "kmk";
  el.style.background = color;
  // 색상별 발광(glow) — 8자리 hex 알파로 같은 색의 후광.
  el.style.boxShadow = `0 0 0 4px ${color}33, 0 0 14px ${color}cc`;
  el.textContent = r.count;
  el.title = `${r.location} · ${r.pest_kr} (${r.count}건)`;
  return el;
}

function render() {
  if (!MAP) return;
  overlays.forEach((o) => o.marker.remove());
  overlays = [];

  const data = aggregate();
  if (!data.length) {
    setSheet("결과 없음", "이 조건에 맞는 제보가 없어요", "risk-none", "—", "필터를 바꿔보세요.");
    document.querySelector("#reportlist").innerHTML = "";
    return;
  }

  let minLng = 180, minLat = 90, maxLng = -180, maxLat = -90;
  data.forEach((r) => {
    const el = makeMarkerEl(r);
    el.addEventListener("click", (e) => { e.stopPropagation(); select(r); });
    const marker = new maplibregl.Marker({ element: el }).setLngLat([r.lng, r.lat]).addTo(MAP);
    overlays.push({ marker, el, data: r });
    if (r.lng < minLng) minLng = r.lng;
    if (r.lng > maxLng) maxLng = r.lng;
    if (r.lat < minLat) minLat = r.lat;
    if (r.lat > maxLat) maxLat = r.lat;
  });

  // 시트가 하단을 가리므로 아래쪽 패딩을 크게.
  MAP.fitBounds([[minLng, minLat], [maxLng, maxLat]], {
    padding: { top: 80, bottom: 230, left: 50, right: 50 },
    maxZoom: 14, duration: 0,
  });

  const focused = FOCUS_LOC ? data.find((r) => normalizeLoc(r.location) === FOCUS_LOC) : null;
  const selected = focused || data[0];
  select(selected);
  renderList(data.filter((r) => r !== selected).slice(0, 5));
}

function select(r) {
  setSheet(r.location, `${r.pest_kr} · 제보 ${r.count}건 · 가장 최근 ${ago(r.recent)}`,
           RISK_CLASS[r.level] || "risk-none", RISK_LABEL[r.level] || "정보 없음", r.hint || "");
  // 선택 마커 강조
  overlays.forEach((o) => o.el.classList.toggle("kmk-sel", o.data === r));
  // 시트 위로 보이게 살짝 위로 당겨 센터링.
  if (MAP) MAP.easeTo({ center: [r.lng, r.lat], offset: [0, -70], duration: 400 });
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
function normalizeLoc(s) {
  return String(s || "").replace(/\s+/g, "");
}

// MapLibre SDK 로드 후 시작.
if (window.maplibregl) {
  initMap();
} else {
  console.error("MapLibre GL 로드 실패 — CDN 연결을 확인하세요.");
}
