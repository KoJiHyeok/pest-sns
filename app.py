"""SNS 해충 탐지 데모 — Streamlit 시각 앱.

문장 입력 → .tflite 모델 예측 → 예측 해충 + 클래스별 확률 막대그래프.
실행:  ../.venv/Scripts/streamlit.exe run app.py
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import predict as P

st.set_page_config(page_title="SNS 해충 탐지", page_icon="🐛", layout="centered")


@st.cache_resource
def get_model():
    # 모델·사전·라벨맵 로드는 무거우니 1회만 (앱 세션 내 캐시)
    return P.load()


@st.cache_data
def get_pest_info():
    # 해충별 예방정보 (research/새 텍스트 문서.md 정제본)
    return json.loads((Path(__file__).parent / "pest_info.json").read_text(encoding="utf-8"))


vectorizer, interp, label_map = get_model()

st.title("🐛 SNS 해충 탐지 데모")
st.caption("문장을 넣으면 어떤 해충 이야기인지 모델이 분류합니다. "
           "학습된 클래스: 빈대·바퀴벌레·러브버그·모기·진드기·말벌 + 해충 없음(7종).")

EXAMPLES = [
    "수원역에서 말벌 때문에 불편합니다",
    "여의도공원에서 모기 때문에 불편합니다",
    "광화문에서 러브버그 발견, 방역 필요해요",
    "오늘 날씨가 좋네요",
]

# 예시 버튼: 누르면 입력칸 값을 채운다. (text_input 생성 '전에' session_state를 세팅해야 함)
if "text" not in st.session_state:
    st.session_state.text = EXAMPLES[0]

st.write("**예시로 빠르게 시도:**")
cols = st.columns(len(EXAMPLES))
for i, ex in enumerate(EXAMPLES):
    if cols[i].button(f"예시 {i + 1}", help=ex, use_container_width=True):
        st.session_state.text = ex

text = st.text_input("문장 입력", key="text")

if text.strip():
    en, kor, probs, order = P.predict(text, vectorizer, interp, label_map)
    conf = float(max(probs))

    st.markdown(f"## 예측 → **{kor}**  `{en}`")
    st.progress(conf, text=f"확신도 {conf * 100:.0f}%")

    df = (
        pd.DataFrame({"해충": [P.KOR.get(o, o) for o in order], "확률": probs})
        .sort_values("확률", ascending=False)
        .set_index("해충")
    )
    st.bar_chart(df, horizontal=True)
    st.caption("⚠️ 학습 데이터(120문장)를 외운 데모 모델입니다. "
               "학습에 없던 단어형엔 약할 수 있어요.")

    # ── 예방 가이드 (리서치 연동) ──
    if en == "none":
        st.success("해충 신호가 감지되지 않았습니다 (해충 없음).")
    else:
        info = get_pest_info().get(en)
        if info:
            st.divider()
            st.subheader(f"🛡️ {info['title']} — 예방 가이드")
            if info.get("risk"):
                st.markdown(f"**위험도**: {info['risk']}")
            for label, key in [("특징", "summary"), ("권장 의류", "clothing"),
                               ("예방법", "prevention"), ("주의사항", "caution"),
                               ("기피성분", "repellent")]:
                if info.get(key):
                    st.markdown(f"- **{label}**: {info[key]}")
            st.caption("출처: research/새 텍스트 문서.md")
