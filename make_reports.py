"""가상 해충 제보 데이터 대량 생성 (지도 데모용).

출력:
  web/data/reports.json  — 제보들 (text, pest_label, location, minutes_ago)
  web/data/geocode.json  — 지명→좌표 (근사 기본값; geocode.py 로 정밀 재생성 가능)
"""
import json
import random
from collections import Counter
from pathlib import Path

random.seed(42)            # 재현성
N = 500

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "web" / "data"
DATA.mkdir(parents=True, exist_ok=True)

# (지명, 위도, 경도) — 데모 기본 좌표(근사). geocode.py(Kakao REST)로 정밀 갱신 가능.
LOCATIONS = [
    ("강남역", 37.4979, 127.0276), ("홍대입구역", 37.5572, 126.9237),
    ("잠실역", 37.5133, 127.1001), ("여의도공원", 37.5266, 126.9241),
    ("광화문", 37.5759, 126.9769), ("서울숲", 37.5444, 127.0374),
    ("신촌역", 37.5551, 126.9368), ("건대입구역", 37.5403, 127.0701),
    ("성수역", 37.5447, 127.0560), ("이태원역", 37.5345, 126.9947),
    ("노원역", 37.6542, 127.0613), ("사당역", 37.4765, 126.9816),
    ("천호역", 37.5385, 127.1238), ("은평 불광천", 37.6005, 126.9200),
    ("뚝섬한강공원", 37.5300, 127.0700), ("수원역", 37.2659, 127.0007),
    ("안양역", 37.4017, 126.9229), ("정자역", 37.3669, 127.1083),
    ("일산 호수공원", 37.6584, 126.7700), ("송도", 37.3894, 126.6390),
    ("부천역", 37.4843, 126.7831), ("의정부역", 37.7385, 127.0458),
    ("모란역", 37.4327, 127.1290), ("광교호수공원", 37.2855, 127.0640),
    ("동탄", 37.2010, 127.0750),
]

# pest_label: (가중치, [문장 템플릿])  — 6월 기준 러브버그·모기 비중↑
PESTS = {
    "none":      (30, ["{loc}에서 점심 먹었어요", "{loc} 산책 좋네요", "{loc} 날씨 맑아요",
                        "{loc} 카페에서 공부 중", "{loc} 사람 많네요"]),
    "mosquito":  (18, ["{loc}에서 모기 때문에 너무 가려워요", "{loc} 모기 떼로 봤어요",
                        "{loc} 근처 모기 진짜 많아요", "{loc}에서 모기 물렸어요"]),
    "lovebug":   (14, ["{loc}에 러브버그 엄청 많아요", "{loc}에서 러브버그 떼 봤어요",
                        "{loc} 러브버그 방역 필요해요"]),
    "wasp":      (10, ["{loc}에서 말벌 보여서 무서워요", "{loc} 말벌집 있는 것 같아요",
                        "{loc} 말벌 때문에 불편합니다"]),
    "tick":      (10, ["{loc} 풀숲에서 진드기 봤어요", "{loc} 산책하다 진드기 물렸어요",
                        "{loc} 진드기 조심하세요"]),
    "cockroach":  (9, ["{loc} 근처에서 바퀴벌레 나왔어요", "{loc} 바퀴벌레 보여요"]),
    "bedbug":     (9, ["{loc} 숙소에서 빈대 나왔어요", "{loc} 빈대 의심돼요"]),
}
labels = list(PESTS)
weights = [PESTS[l][0] for l in labels]

reports = []
for i in range(N):
    name, _, _ = random.choice(LOCATIONS)
    label = random.choices(labels, weights=weights)[0]
    tpl = random.choice(PESTS[label][1])
    reports.append({
        "id": i + 1,
        "text": tpl.format(loc=name),
        "pest_label": label,
        "location": name,
        "minutes_ago": random.randint(2, 20160),   # 최근 ~14일 (필터 '오늘'이 의미있게 걸러지도록)
    })

(DATA / "reports.json").write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")

# geocode.json 은 '없을 때만' 생성 — geocode.py(REST)로 받아둔 정밀 좌표를 덮어쓰지 않기 위함.
geo_path = DATA / "geocode.json"
if geo_path.exists():
    geo_note = f"기존 유지({len(json.loads(geo_path.read_text(encoding='utf-8')))}곳)"
else:
    geo = {name: {"lat": lat, "lng": lng} for name, lat, lng in LOCATIONS}
    geo_path.write_text(json.dumps(geo, ensure_ascii=False, indent=2), encoding="utf-8")
    geo_note = f"신규 생성({len(geo)}곳, 근사 좌표)"

print(f"reports.json: {len(reports)}건 / {len(LOCATIONS)}곳")
print("pest 분포:", dict(Counter(r["pest_label"] for r in reports)))
print(f"geocode.json: {geo_note}")
