# -*- coding: utf-8 -*-
"""THAI LOTTERY AI - Streamlit dashboard aligned with LAO DEVELOPMENT AI layout."""
from pathlib import Path
from collections import Counter
import csv
import io

import pandas as pd
import streamlit as st

from thai_engine import (
    from_thai_csv, from_thai_web, save_thai_csv, dedupe_thai,
    expand_prize_rows, rank_thai, thai_backtest_comparison, kind,
    rank_sets, rank_daily_sets, rank_hybrid_sets, WEEKDAY_NAMES,
)

st.set_page_config(
    page_title="THAI LOTTERY AI",
    page_icon="🇹🇭",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = BASE_DIR / "history_thai.csv"
WEEKDAY_LABELS = WEEKDAY_NAMES + ["ทุกวัน (รวม)"]
WEEKDAY_VALUES = [str(i) for i in range(7)] + ["all"]
PRIZE_FIELDS = [
    ("รางวัลที่ 1 · 6 ตัว", "six"),
    ("เลขหน้า 3 ตัว", "front3"),
    ("เลขท้าย 3 ตัว", "back3"),
    ("2 ตัวบน · 2 หลักท้ายรางวัลที่ 1", "top2"),
    ("เลขท้าย 2 ตัว · รางวัลจริง", "last2"),
    ("เลข 5 ตัวท้ายจากรางวัลที่ 1", "suffix5"),
    ("เลข 4 ตัวท้ายจากรางวัลที่ 1", "suffix4"),
]

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1450px;}
.hero {padding: 1.25rem 1.5rem; border-radius: 16px; background: linear-gradient(115deg,#123b35,#246b5a); color: white; margin-bottom: 1rem;}
.hero h1 {font-size: 2rem; margin: 0;}
.hero p {margin: .35rem 0 0 0; opacity: .88;}
div[data-testid="stMetric"] {background: var(--secondary-background-color); padding: 14px; border-radius: 12px;}
</style>
<div class="hero">
<h1>THAI LOTTERY AI</h1>
<p>THAI GOVERNMENT LOTTERY · HISTORICAL + DAILY + HYBRID ENGINE</p>
</div>
""", unsafe_allow_html=True)


def normalize_rows(rows):
    return dedupe_thai(rows or [])


def get_rows():
    if "thai_rows_all" not in st.session_state:
        if DEFAULT_CSV.exists():
            st.session_state.thai_rows_all = normalize_rows(from_thai_csv(str(DEFAULT_CSV)))
            st.session_state.thai_source = "history_thai.csv ใน Repository"
        else:
            st.session_state.thai_rows_all = []
            st.session_state.thai_source = "ยังไม่ได้โหลดข้อมูล"
    return st.session_state.thai_rows_all


def load_uploaded(uploaded):
    text = uploaded.getvalue().decode("utf-8-sig")
    tmp = Path("/tmp/history_thai_upload.csv")
    tmp.write_text(text, encoding="utf-8-sig")
    return normalize_rows(from_thai_csv(str(tmp)))


def rows_to_frame(rows):
    return pd.DataFrame([{
        "วันที่": r["date"].strftime("%d/%m/%Y"),
        "วัน": WEEKDAY_NAMES[r["date"].weekday()],
        "รางวัลที่ 1": r["six"],
        "2 ตัวบน": r["six"][-2:],
        "เลขท้าย 2 ตัว (รางวัลจริง)": r["last2"],
        "เลขหน้า 3 ตัว": f'{r["front3_1"]}  {r["front3_2"]}',
        "เลขท้าย 3 ตัว": f'{r["back3_1"]}  {r["back3_2"]}',
    } for r in rows])


def rank_frame(items):
    return pd.DataFrame([{
        "อันดับ": i, "หมายเลข": x["number"], "คะแนน": x["score"], "รูปแบบ": x["type"]
    } for i, x in enumerate(items, 1)])


def prize_observations(rows, field):
    """Convert one prize group to independent observations for the shared engines."""
    expanded = expand_prize_rows(rows, field)
    return [{**r, "analysis": r["value"]} for r in expanded]


def digit_profile(rows, field):
    observations = prize_observations(rows, field)
    if not observations:
        return [], Counter(), []
    counts = Counter("".join(x["analysis"] for x in observations))
    positions = [Counter(x["analysis"][i] for x in observations)
                 for i in range(len(observations[0]["analysis"]))]
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return positions, counts, ranked


def csv_bytes(rows):
    buf = io.StringIO()
    save_thai_csv(rows, buf)
    return buf.getvalue().encode("utf-8-sig")


all_rows = get_rows()

with st.sidebar:
    st.header("ตั้งค่าการวิเคราะห์")
    selected_label = st.selectbox("เลือกวันวิเคราะห์", WEEKDAY_LABELS, index=0)
    selected_day = WEEKDAY_VALUES[WEEKDAY_LABELS.index(selected_label)]
    selected_prize_label = st.selectbox(
        "ประเภทรางวัลสำหรับเลขเด่น/เลขรอง",
        [x[0] for x in PRIZE_FIELDS],
        index=0,
    )
    selected_prize = dict(PRIZE_FIELDS)[selected_prize_label]
    st.divider()
    st.subheader("ฐานข้อมูล")
    st.caption(f"แหล่งข้อมูล: {st.session_state.get('thai_source', 'ยังไม่ได้โหลดข้อมูล')}")
    uploaded = st.file_uploader("นำเข้าไฟล์ CSV", type=["csv"])
    if uploaded is not None and st.button("ใช้ไฟล์ CSV ที่เลือก", use_container_width=True):
        try:
            st.session_state.thai_rows_all = load_uploaded(uploaded)
            st.session_state.thai_source = f"CSV Upload: {uploaded.name}"
            st.success(f"โหลดข้อมูล {len(st.session_state.thai_rows_all):,} งวดแล้ว")
            st.rerun()
        except Exception as exc:
            st.error(f"อ่าน CSV ไม่สำเร็จ: {type(exc).__name__}: {exc}")
    if st.button("UPDATE DATA · ThaiORC", use_container_width=True, type="primary"):
        try:
            with st.spinner("กำลังดึงและตรวจสอบข้อมูลจาก ThaiORC..."):
                fresh, source = from_thai_web(10, 50)
                st.session_state.thai_rows_all = normalize_rows(fresh)
                st.session_state.thai_source = f"ThaiORC: {source}"
                st.success(f"อัปเดตสำเร็จ {len(st.session_state.thai_rows_all):,} งวด")
                st.rerun()
        except Exception as exc:
            st.error(f"อัปเดตไม่สำเร็จ: {type(exc).__name__}: {exc}")

all_rows = normalize_rows(st.session_state.thai_rows_all)
if selected_day == "all":
    rows_selected = all_rows
else:
    weekday = int(selected_day)
    rows_selected = [r for r in all_rows if r["date"].weekday() == weekday]

if not all_rows:
    st.warning("ยังไม่มีฐานข้อมูล กรุณาอัปโหลด CSV หรือกด UPDATE DATA จากแถบด้านซ้าย")
    st.stop()

latest = all_rows[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("จำนวนงวดทั้งหมด", f"{len(all_rows):,}")
c2.metric("งวดของวันที่เลือก", f"{len(rows_selected):,}")
c3.metric("ผลล่าสุดในฐานข้อมูล", latest["six"])
c4.metric("วันที่ล่าสุด", latest["date"].strftime("%d/%m/%Y"))
st.caption(f"แหล่งข้อมูล: {st.session_state.get('thai_source', '')}")

# Match the same six-tab navigation pattern as LAO DEVELOPMENT AI.
tabs = st.tabs(["ภาพรวม", "AI Analysis", "Daily + Hybrid", "Double Engine", "Backtest", "ฐานข้อมูล"])

with tabs[0]:
    st.subheader("ภาพรวมฐานข้อมูล")
    st.write(f"ช่วงข้อมูล: **{all_rows[0]['date']:%d/%m/%Y} – {all_rows[-1]['date']:%d/%m/%Y}**")
    weekday_counts = Counter(r["date"].weekday() for r in all_rows)
    st.dataframe(pd.DataFrame([
        {"วัน": WEEKDAY_NAMES[i], "จำนวนงวด": weekday_counts[i]} for i in range(7)
    ]), use_container_width=True, hide_index=True)
    _, overall, _ = digit_profile(all_rows, selected_prize)
    freq_df = pd.DataFrame([{"เลข": d, "จำนวนครั้ง": overall[d]} for d in "0123456789"])
    st.subheader(f"ความถี่ตัวเลขรวม · {selected_prize_label}")
    st.bar_chart(freq_df.set_index("เลข"))
    st.info("ข้อมูลรางวัลแต่ละประเภทถูกแยกวิเคราะห์ ไม่รวมเลขต่างประเภทรางวัลเข้าด้วยกัน")

with tabs[1]:
    st.subheader(f"AI Analysis · {selected_label}")
    if len(rows_selected) < 1:
        st.warning("ไม่มีข้อมูลสำหรับวันที่เลือก")
    elif st.button("เริ่ม AI Analysis", key="run_analysis", type="primary"):
        positions, overall, ranked = digit_profile(rows_selected, selected_prize)
        a, b, c = st.columns(3)
        a.metric("เลขเด่น · MAIN", " - ".join(d for d, _ in ranked[:3]) or "ไม่มีข้อมูล")
        b.metric("เลขรอง · SECONDARY", " - ".join(d for d, _ in ranked[3:6]) or "ไม่มีข้อมูล")
        c.metric("จำนวนรายการ", f"{sum(overall.values()):,}")
        st.markdown(f"**ผลรางวัลล่าสุดของ {selected_label}**")
        latest_day = rows_selected[-1]
        st.write(
            f'รางวัลที่ 1 `{latest_day["six"]}` · เลขหน้า 3 ตัว '
            f'`{latest_day["front3_1"]} {latest_day["front3_2"]}` · '
            f'เลขท้าย 3 ตัว `{latest_day["back3_1"]} {latest_day["back3_2"]}` · '
            f'2 ตัวบน `{latest_day["six"][-2:]}` · '
            f'เลขท้าย 2 ตัว (รางวัลจริง) `{latest_day["last2"]}`'
        )
        st.markdown("**ความถี่รายหลัก**")
        st.dataframe(pd.DataFrame([
            {"ตำแหน่ง": f"หลักที่ {i+1}", **{d: counts[d] for d in "0123456789"}}
            for i, counts in enumerate(positions)
        ]), use_container_width=True, hide_index=True)
        st.markdown("**ผลจัดอันดับแยกตามประเภทรางวัล**")
        for label, field in PRIZE_FIELDS:
            with st.expander(label, expanded=(field == selected_prize)):
                try:
                    st.dataframe(rank_frame(rank_thai(rows_selected, field, 10, "historical")),
                                 use_container_width=True, hide_index=True)
                except ValueError as exc:
                    st.warning(str(exc))

with tabs[2]:
    st.subheader(f"Daily + Hybrid Engine · {selected_label}")
    st.caption("Daily ใช้ข้อมูลทุกวัน 20 งวดล่าสุด · Hybrid = Historical ของวันที่เลือก 60% + Daily 40%")
    if len(all_rows) < 5 or len(rows_selected) < 5:
        st.warning("ต้องมีข้อมูลอย่างน้อย 5 งวด ทั้งฐานข้อมูลรวมและวันที่เลือก จึงจะคำนวณ Daily + Hybrid ได้")
    elif st.button("คำนวณ Daily + Hybrid", key="run_hybrid", type="primary"):
        for label, field in PRIZE_FIELDS:
            daily_data = prize_observations(all_rows, field)
            historical_data = prize_observations(rows_selected, field)
            with st.expander(label, expanded=(field == selected_prize)):
                left, right = st.columns(2)
                try:
                    with left:
                        st.markdown("**DAILY ENGINE · TOP 10**")
                        st.dataframe(rank_frame(rank_daily_sets(daily_data, "analysis", 10, 20)),
                                     use_container_width=True, hide_index=True)
                    with right:
                        st.markdown("**HYBRID ENGINE · TOP 10**")
                        st.dataframe(rank_frame(rank_hybrid_sets(
                            historical_data, daily_data, "analysis", 10, 20, .60
                        )), use_container_width=True, hide_index=True)
                except ValueError as exc:
                    st.warning(str(exc))

with tabs[3]:
    st.subheader(f"Double Engine · {selected_label}")
    if len(rows_selected) < 1:
        st.warning("ไม่มีข้อมูลสำหรับวันที่เลือก")
    elif st.button("วิเคราะห์เลขซ้ำ", key="double_run", type="primary"):
        samples = prize_observations(rows_selected, selected_prize)
        counts = Counter(kind(x["analysis"]) for x in samples)
        total = len(samples)
        st.dataframe(pd.DataFrame([
            {"รูปแบบ": pattern, "จำนวน": counts[pattern],
             "สัดส่วน": f"{counts[pattern] / total:.2%}" if total else "0.00%"}
            for pattern in ["เลขเดี่ยว", "เบิ้ล", "เบิ้ลคู่", "มีตอง", "ตอง", "เหมือนกันทั้งหมด"]
        ]), use_container_width=True, hide_index=True)
        st.markdown("**ชุดเลขซ้ำที่จัดอันดับได้**")
        try:
            doubles = [x for x in rank_thai(rows_selected, selected_prize, 100, "historical")
                       if x["type"] in ("เบิ้ล", "เบิ้ลคู่", "มีตอง", "ตอง", "เหมือนกันทั้งหมด")]
            st.dataframe(rank_frame(doubles), use_container_width=True, hide_index=True)
        except ValueError as exc:
            st.warning(str(exc))

with tabs[4]:
    st.subheader(f"WALK-FORWARD BACKTEST · {selected_label}")
    st.caption("ทดสอบเฉพาะงวดของวันที่เลือก โดยใช้ข้อมูลก่อนงวดเป้าหมายเท่านั้น")
    test_count = st.selectbox(
        "จำนวนงวดทดสอบล่าสุด",
        [20, 30, 60, 100, 200],
        index=1,
        help="ใช้ Walk-forward: ทุกงวดทดสอบจะใช้เฉพาะข้อมูลที่มาก่อนงวดนั้น",
    )
    available_test_draws = max(0, len(rows_selected) - 10)
    actual_test_draws = min(test_count, available_test_draws)
    st.caption(
        f"เปรียบเทียบ AI Top 10 กับ Random Top 10 เฉพาะข้อมูลตามวันที่เลือก: "
        f"มีข้อมูล {len(rows_selected)} งวด · กัน 10 งวดแรกไว้เป็นข้อมูลตั้งต้น · "
        f"ทดสอบได้สูงสุด {available_test_draws} งวด"
    )
    st.info(
        f"คุณเลือกทดสอบ {test_count} งวด แต่จากข้อมูลของวันที่เลือกในฐานข้อมูล "
        f"จะทดสอบได้จริง {actual_test_draws} งวด"
        if actual_test_draws < test_count
        else f"ข้อมูลของวันที่เลือกเพียงพอสำหรับทดสอบ {actual_test_draws} งวด"
    )
    if available_test_draws < 1:
        st.warning("ข้อมูลของวันที่เลือกยังไม่เพียงพอ ต้องมีมากกว่า 10 งวดเพื่อเริ่ม Backtest")
    elif st.button("เริ่ม Backtest", key="backtest_run", type="primary"):
        with st.spinner("กำลังทดสอบย้อนหลังและเปรียบเทียบ Random..."):
            results = thai_backtest_comparison(rows_selected, 10, test_count)
            table = []
            for name, item in results.items():
                tested = item["tested"]
                ai_rate = f'{item["ai_rate"]:.2%}' if tested else "ไม่มีข้อมูล"
                random_rate = f'{item["random_rate"]:.2%}' if tested else "ไม่มีข้อมูล"
                delta = f'{(item["ai_rate"] - item["random_rate"]):+.2%}' if tested else "ไม่มีข้อมูล"
                table.append({
                    "ประเภทรางวัล": name,
                    "AI ถูก": f'{item["ai_hits"]}/{tested}',
                    "AI อัตราตรง": ai_rate,
                    "Random ถูก": f'{item["random_hits"]}/{tested}',
                    "Random อัตราตรง": random_rate,
                    "AI − Random": delta,
                })
            st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
            tested_values = [item["tested"] for item in results.values()]
            actual_done = max(tested_values, default=0)
            st.caption(
                f"วันที่เลือก: {selected_label} · เลือกทดสอบ {test_count} งวด · "
                f"ทดสอบจริง {actual_done} งวด · AI Top 10 เทียบ Random Top 10 "
                "ด้วยงวดเดียวกันและการสุ่มแบบทำซ้ำได้"
            )
            st.caption("ผล Backtest เป็นผลย้อนหลัง ไม่รับประกันผลในอนาคต")

with tabs[5]:
    st.subheader(f"ฐานข้อมูล · {selected_label}")
    st.dataframe(rows_to_frame(rows_selected).iloc[::-1], use_container_width=True, hide_index=True)
    st.download_button(
        "ดาวน์โหลดฐานข้อมูล CSV ทั้งหมด",
        data=csv_bytes(all_rows),
        file_name="history_thai.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.divider()
st.caption("THAI LOTTERY AI · Statistical research tool only. คะแนนเป็นอันดับสัมพัทธ์ ไม่ใช่ความน่าจะเป็นหรือการรับประกันผลรางวัล.")
