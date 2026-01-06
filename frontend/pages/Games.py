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
    list_genres,
    list_publishers,
    get_date_bounds,
    get_top_games_filtered,
    get_game_daily_trend,
)

init_page()
render_header()
render_sidebar()

section_title("Games Explorer", icon="🎮")
st.caption("Esplora giochi con filtri e drill-down: classifica, KPI e trend temporale del gioco selezionato.")

# ------------------------------
# Filtri
# ------------------------------
min_day, max_day = get_date_bounds()

with st.container():
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 1])

    with c1:
        top_n = st.slider("Top N", 10, 200, 30, 10)

    with c2:
        min_reviews = st.number_input("Min recensioni", min_value=0, value=50, step=50)

    with c3:
        order_by = st.selectbox("Ordina per", ["reviews", "avg_sentiment", "avg_votes_up"], index=0)

    with c4:
        free_to_play = st.selectbox("Free-to-play", ["All", "Yes", "No"], index=0)

with st.container():
    c5, c6, c7, c8 = st.columns([1.2, 1.2, 1.2, 1.2])

    with c5:
        required_age = st.selectbox("Required age", ["All", "0", "18+"], index=0)

    with c6:
        genre_opts = ["All"] + list_genres()
        genre = st.selectbox("Genre", genre_opts, index=0)

    with c7:
        pub_opts = ["All"] + list_publishers()
        publisher = st.selectbox("Publisher", pub_opts, index=0)

    with c8:
        # date range solo se disponibile
        if min_day is None or max_day is None:
            st.caption("Date range: N/A")
            date_from = None
            date_to = None
        else:
            date_range = st.date_input("Date range", value=(min_day, max_day))
            # Streamlit può restituire 1 o 2 date
            if isinstance(date_range, tuple) and len(date_range) == 2:
                date_from, date_to = date_range
            else:
                date_from, date_to = min_day, max_day

section_divider()

# ------------------------------
# Top games filtrati
# ------------------------------
df = get_top_games_filtered(
    limit=int(top_n),
    min_reviews=int(min_reviews),
    date_from=date_from,
    date_to=date_to,
    free_to_play=free_to_play,
    required_age=required_age,
    genre=genre,
    publisher=publisher,
    order_by=order_by,
)

if df.empty:
    st.info(
        "Nessun risultato: il DW potrebbe essere vuoto oppure i filtri sono troppo restrittivi.\n\n"
        "Prova a mettere Min recensioni = 0 e rimuovere Genre/Publisher."
    )
    render_footer()
    st.stop()

st.subheader("Top games (filtrati)")
st.dataframe(df, use_container_width=True, hide_index=True)

section_divider()

# ------------------------------
# Drill-down: trend del gioco selezionato
# ------------------------------
st.subheader("Drill-down: trend gioco selezionato")

names = df["name"].tolist()
selected_name = st.selectbox("Seleziona gioco", names, index=0)
selected_id = int(df.loc[df["name"] == selected_name, "id_game"].iloc[0])

trend = get_game_daily_trend(selected_id, date_from=date_from, date_to=date_to)

if trend.empty:
    st.caption("Nessun dato trend per il gioco selezionato nel range scelto.")
else:
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**Recensioni al giorno**")
        st.line_chart(trend.set_index("day")[["reviews"]])
    with t2:
        st.markdown("**Sentiment medio al giorno**")
        st.line_chart(trend.set_index("day")[["avg_sentiment"]])

render_footer()