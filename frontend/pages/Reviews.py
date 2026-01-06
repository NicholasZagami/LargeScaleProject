from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from frontend.utils.layout import (
    init_page,
    render_header,
    render_sidebar,
    render_footer,
    section_title,
    section_divider,
)
from frontend.utils.data_access import (
    get_date_bounds,
    get_reviews_trend_daily,
    get_reviews_kpis,
    get_votes_by_sentiment_bins,
    get_wordcount_bins,
)

init_page()
render_header()
render_sidebar()

section_title("Reviews & Sentiment", icon="💬")
st.caption("Trend e insight sulle recensioni: sentiment, engagement (votes) e lunghezza testo.")

min_day, max_day = get_date_bounds()

with st.container():
    c1, c2 = st.columns([1.6, 1])
    with c1:
        if min_day is None or max_day is None:
            st.caption("Date range: N/A")
            date_from = None
            date_to = None
        else:
            date_range = st.date_input("Date range", value=(min_day, max_day))
            if isinstance(date_range, tuple) and len(date_range) == 2:
                date_from, date_to = date_range
            else:
                date_from, date_to = min_day, max_day

    with c2:
        days = st.slider("Trend window (giorni)", 14, 90, 60, 7)

section_divider()

# KPI
kpi = get_reviews_kpis(date_from=date_from, date_to=date_to)
if kpi is None:
    st.info("DW non pronto o vuoto: carica seed/dati reali per vedere le analisi.")
    render_footer()
    st.stop()

k1, k2, k3 = st.columns(3)
k1.metric("Recensioni", f"{int(kpi['total_reviews']):,}")
k2.metric("Sentiment medio", f"{float(kpi['avg_sentiment'] or 0):.2f}")
k3.metric("Votes up medi", f"{float(kpi['avg_votes_up'] or 0):.2f}")

section_divider()

# Trend (riuso funzione trend daily, filtriamo “a valle” sul range selezionato)
trend = get_reviews_trend_daily(days=int(days))
if trend.empty:
    st.info("Trend non disponibile (DW vuoto).")
else:
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**Recensioni al giorno**")
        st.line_chart(trend.set_index("day")[["reviews"]])
    with t2:
        st.markdown("**Sentiment medio al giorno**")
        st.line_chart(trend.set_index("day")[["avg_sentiment"]])

section_divider()

# Votes vs sentiment (bucket)
section_title("Engagement vs Sentiment", icon="👍")
vs = get_votes_by_sentiment_bins(date_from=date_from, date_to=date_to)
if vs.empty:
    st.caption("N/A")
else:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Numero recensioni per sentiment**")
        st.bar_chart(vs.set_index("sentiment_round")[["n"]])
    with c2:
        st.markdown("**Votes up medi per sentiment**")
        st.line_chart(vs.set_index("sentiment_round")[["avg_votes_up"]])

section_divider()

# Wordcount bins
section_title("Lunghezza testo e sentiment", icon="🧾")
wc = get_wordcount_bins(date_from=date_from, date_to=date_to)
if wc.empty:
    st.caption("N/A")
else:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Distribuzione lunghezza recensioni**")
        st.bar_chart(wc.set_index("wc_bin")[["n"]])
    with c2:
        st.markdown("**Sentiment medio per lunghezza**")
        st.line_chart(wc.set_index("wc_bin")[["avg_sentiment"]])

render_footer()
