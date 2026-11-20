# -*- coding: utf-8 -*-
"""THAI LOTTERY AI - Streamlit Cloud dashboard."""
from collections import Counter
from datetime import datetime
import io
from pathlib import Path
import pandas as pd
import streamlit as st

from thai_engine import (
    from_thai_csv, from_thai_web, save_thai_csv, dedupe_thai,
    rank_thai, thai_backtest, kind, expand_prize_rows, WEEKDAY_NAMES
)

st.set_page_config(
    page_title="THAI LOTTERY AI",
    page_icon="🇹🇭",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = BASE_DIR / "history_thai.csv"
FIELDS = [
    ("รางวัลที่ 1 · 6 ตัว", "six"),
    ("เลขหน้า 3 ตัว", "front3"),
    ("เลขท้าย 3 ตัว", "back3"),
    ("เลขท้าย 2 ตัว", "last2"),
    ("เลข 5 ตัวท้ายจากรางวัลที่ 1", "suffix5"),
    ("เลข 4 ตัวท้ายจากรางวัลที่ 1", "suffix4"),
]

st.markdown("""
<style>
.block-container {padding-top:1.5rem;padding-bottom:2rem;max-width:1450px;}
.hero {padding:1.25rem 1.5rem;border-radius:16px;background:linear-gradient(115deg,#17365d,#245b8f);color:white;margin-bottom:1rem;}
.hero h1 {font-size:2rem;margin:0;}
.hero p {margin:.35rem 0 0 0;opacity:.9;}
div[data-testid="stMetric"] {background:var(--secondary-background-color);padding:14px;border-radius:12px;}
</style>
<div class="hero"><h1>THAI LOTTERY AI</h1>
<p>THAI GOVERNMENT LOTTERY · HISTORICAL + DAILY + HYBRID ENGINE</p></div>
""", unsafe_allow_html=True)


def normalize_rows(rows):
    cleaned = dedupe_thai(rows or [])
    return sorted(cleaned, key=lambda r: r["date"])


def get_rows():
    if "thai_rows" not in st.session_state:
        if DEFAULT_CSV.exists():
            st.session_state.thai_rows = normalize_rows(from_thai_csv(str(DEFAULT_CSV)))
            st.session_state.thai_source = "history_thai.csv ใน Repository"
        else:
            st.session_state.thai_rows = []
            st.session_state.thai_source = "ยังไม่ได้โหลดข้อมูล"
    return st.session_state.thai_rows


def frame(rows):
    return pd.DataFrame([{
        "วันที่": r["date"].strftime("%d/%m/%Y"),
        "รางวัลที่ 1": r["six"],
        "เลขท้าย 2 ตัว": r["last2"],
        "เลขหน้า 3 ตัว": f'{r["front3_1"]}  {r["front3_2"]}',
        "เลขท้าย 3 ตัว": f'{r["back3_1"]}  {r["back3_2"]}',
    } for r in rows])


def rank_frame(items):
    return pd.DataFrame([
        {"อันดับ": i, "หมายเลข": x["number"], "คะแนน": x["score"], "รูปแบบ": x["type"]}
        for i, x in enumerate(items, 1)
    ])


def save_bytes(rows):
    buf = io.StringIO()
    save_thai_csv(rows, buf)
    return buf.getvalue().encode("utf-8-sig")


get_rows()

with st.sidebar:
    st.header("ตั้งค่าการวิเคราะห์")
    st.caption("หวยรัฐบาลไทย · วิเคราะห์ตามงวด ไม่กรองวันจันทร์–ศุกร์")
    st.divider()
    st.subheader("ฐานข้อมูล")
    st.caption(f"แหล่งข้อมูล: {st.session_state.get('thai_source', '')}")

    upload = st.file_uploader("นำเข้า history_thai.csv", type=["csv"])
    if upload is not None and st.button("ใช้ไฟล์ CSV ที่เลือก", use_container_width=True):
        try:
            text = upload.getvalue().decode("utf-8-sig")
            tmp = Path("/tmp/history_thai_upload.csv")
            tmp.write_text(text, encoding="utf-8-sig")
            st.session_state.thai_rows = normalize_rows(from_thai_csv(str(tmp)))
            st.session_state.thai_source = f"CSV Upload: {upload.name}"
            st.rerun()
        except Exception as exc:
            st.error(f"อ่าน CSV ไม่สำเร็จ: {exc}")

    if st.button("UPDATE DATA · ThaiORC", type="primary", use_container_width=True):
        try:
            with st.spinner("กำลังดึงสถิติหวยรัฐบาลไทยจาก ThaiORC..."):
                fresh, source = from_thai_web(10, 50)
                merged = normalize_rows(list(st.session_state.thai_rows) + list(fresh))
                st.session_state.thai_rows = merged
                st.session_state.thai_source = f"ThaiORC: {source}"
                st.success(f"อัปเดตสำเร็จ รวม {len(merged):,} งวด")
                st.rerun()
        except Exception as exc:
            st.error(f"อัปเดตไม่สำเร็จ: {type(exc).__name__}: {exc}")

rows = st.session_state.thai_rows
if not rows:
    st.warning("ยังไม่มีฐานข้อมูล กรุณานำเข้า CSV หรือกด UPDATE DATA จากแถบด้านซ้าย")
    st.stop()

latest = rows[-1]
a, b, c, d = st.columns(4)
a.metric("จำนวนงวด", f"{len(rows):,}")
b.metric("รางวัลที่ 1 ล่าสุด", latest["six"])
c.metric("เลขท้าย 2 ตัว", latest["last2"])
d.metric("วันที่ล่าสุด", latest["date"].strftime("%d/%m/%Y"))
st.caption(f"แหล่งข้อมูล: {st.session_state.get('thai_source', '')}")

tabs = st.tabs(["ภาพรวม", "AI Analysis", "Daily + Hybrid", "Double Engine", "Backtest", "ฐานข้อมูล"])

with tabs[0]:
    st.subheader("ภาพรวมผลรางวัลรัฐบาลไทย")
    st.write(f'ช่วงข้อมูล: **{rows[0]["date"]:%d/%m/%Y} – {rows[-1]["date"]:%d/%m/%Y}**')
    st.dataframe(frame(rows).iloc[::-1], use_container_width=True, hide_index=True)
    st.info("ข้อมูลรางวัลแต่ละประเภทถูกแยกวิเคราะห์ ไม่รวมเลขต่างประเภทรางวัลเข้าด้วยกัน")

with tabs[1]:
    st.subheader("HISTORICAL AI ANALYSIS")
    choice = st.selectbox("เลือกประเภทรางวัล", FIELDS, format_func=lambda x: x[0], key="hist_field")
    if st.button("เริ่ม AI Analysis", type="primary", key="hist_run"):
        try:
            st.dataframe(rank_frame(rank_thai(rows, choice[1], 10, "historical")), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(str(exc))

with tabs[2]:
    st.subheader("DAILY + HYBRID ENGINE")
    st.caption("Daily ใช้ข้อมูล 20 รายการล่าสุดของประเภทรางวัลนั้น · Hybrid ผสาน Historical 60% + Daily 40%")
    choice = st.selectbox("เลือกประเภทรางวัล", FIELDS, format_func=lambda x: x[0], key="daily_field")
    if st.button("คำนวณ Daily + Hybrid", type="primary", key="daily_run"):
        try:
            left, right = st.columns(2)
            with left:
                st.markdown("**DAILY ENGINE · TOP 10**")
                st.dataframe(rank_frame(rank_thai(rows, choice[1], 10, "daily", 20)), use_container_width=True, hide_index=True)
            with right:
                st.markdown("**HYBRID ENGINE · TOP 10**")
                st.dataframe(rank_frame(rank_thai(rows, choice[1], 10, "hybrid", 20)), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(str(exc))

with tabs[3]:
    st.subheader("DOUBLE ENGINE")
    st.caption("วิเคราะห์รูปแบบเบิ้ล ตอง และเลขซ้ำแยกตามประเภทรางวัล")
    choice = st.selectbox("เลือกประเภทรางวัล", FIELDS, format_func=lambda x: x[0], key="double_field")
    if st.button("วิเคราะห์เลขซ้ำ", type="primary", key="double_run"):
        try:
            samples = expand_prize_rows(rows, choice[1])
            counts = Counter(kind(x["value"]) for x in samples)
            total = len(samples)
            if total == 0:
                st.warning("ไม่พบข้อมูลตัวอย่างสำหรับประเภทรางวัลที่เลือก")
            else:
                st.dataframe(pd.DataFrame([
                    {
                        "รูปแบบ": k,
                        "จำนวน": counts[k],
                        "สัดส่วน": f"{counts[k] / total:.2%}",
                    }
                    for k in ["เลขเดี่ยว", "เบิ้ล", "เบิ้ลคู่", "มีตอง", "ตอง", "เหมือนกันทั้งหมด"]
                ]), use_container_width=True, hide_index=True)
                doubles = [
                    x for x in rank_thai(rows, choice[1], 100, "historical")
                    if x["type"] in ("เบิ้ล", "เบิ้ลคู่", "มีตอง", "ตอง")
                ]
                st.markdown("**ชุดเลขซ้ำที่จัดอันดับได้**")
                st.dataframe(rank_frame(doubles), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(str(exc))

with tabs[4]:
    st.subheader("WALK-FORWARD BACKTEST")
    st.caption("ทดสอบจากข้อมูลก่อนงวดเป้าหมายเท่านั้น · Top 10 exact match")
    if len(rows) < 12:
        st.warning("ข้อมูลยังไม่เพียงพอสำหรับ Backtest")
    elif st.button("เริ่ม Backtest", type="primary", key="backtest_run"):
        with st.spinner("กำลังทดสอบย้อนหลัง..."):
            results = thai_backtest(rows, 10, 30)
            st.dataframe(pd.DataFrame([
                {
                    "ประเภทรางวัล": name,
                    "ถูกอย่างน้อยหนึ่งเลข": f"{hit}/{tested}",
                    "อัตราตรงตัว": f"{hit / tested:.2%}" if tested else "ไม่มีข้อมูล",
                }
                for name, (hit, tested) in results.items()
            ]), use_container_width=True, hide_index=True)
            st.caption("ผล Backtest เป็นผลย้อนหลัง ไม่รับประกันผลในอนาคต")

with tabs[5]:
    st.subheader("ฐานข้อมูลหวยรัฐบาลไทย")
    st.dataframe(frame(rows).iloc[::-1], use_container_width=True, hide_index=True)
    st.download_button(
        "ดาวน์โหลด history_thai.csv",
        data=save_bytes(rows),
        file_name="history_thai.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.divider()
st.caption("THAI LOTTERY AI · Statistical research tool only. คะแนนเป็นอันดับสัมพัทธ์ ไม่ใช่ความน่าจะเป็นหรือการรับประกันผลรางวัล.")
