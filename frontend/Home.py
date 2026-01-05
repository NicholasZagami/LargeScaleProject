from __future__ import annotations

from pathlib import Path
import sys

# === Fix path per importare 'frontend' ===
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from frontend.utils.layout import (
    init_page,
    render_header,
    render_sidebar,
    section_title,
    section_divider,
    kpi_card,
    render_footer,
)
from frontend.utils.data_access import (
    get_kpis,
    get_datasets_info,
    get_reviews_trend_daily,
    get_language_distribution,
    get_top_genres,
    get_top_games_home,
)

# === Config & layout comuni ===
init_page()
render_header()
render_sidebar()

# === HERO SECTION ===
from frontend.utils.layout import ASSETS_DIR

hero_img = ASSETS_DIR / "store_home_share.jpg"

st.markdown("<br>", unsafe_allow_html=True)

hero = st.container()
with hero:
    if hero_img.exists():
        st.image(str(hero_img))
    else:
        st.markdown("<h1 style='text-align:center;'>🎮</h1>", unsafe_allow_html=True)

    st.markdown(
        """
        <div style='text-align:center; margin-top:-15px;'>
            <h1 style='font-size:32px; margin-bottom:0;'>Steam Games Data Warehouse</h1>
            <p style='font-size:18px; color:#aaa; margin-top:2px;'>
                Dashboard interattiva su giochi, recensioni e trend del marketplace Steam
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

section_divider()

# === KPI principali ===
kpis = get_kpis()

st.markdown("#### Panoramica rapida")
kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
with kpi_col1:
    kpi_card("Giochi nel catalogo", f"{kpis.total_games:,}")
with kpi_col2:
    kpi_card("Recensioni totali", f"{kpis.total_reviews:,}")
with kpi_col3:
    kpi_card("Rating medio globale", f"{kpis.avg_rating:.2f} ⭐")

section_divider()

# === Trend & Insight ===
section_title("Trend & insight", icon="📈")

trend_days = st.slider("Finestra temporale (giorni)", min_value=14, max_value=90, value=60, step=7)
trend_df = get_reviews_trend_daily(days=trend_days)

if trend_df.empty:
    st.info(
        "Trend non disponibile (DW vuoto o tabelle non popolate). "
        "Con seed o dati reali questa sezione si popola automaticamente."
    )
else:
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Recensioni al giorno**")
        st.line_chart(trend_df.set_index("day")[["reviews"]])

    with c2:
        st.markdown("**Sentiment medio al giorno**")
        st.line_chart(trend_df.set_index("day")[["avg_sentiment"]])

section_divider()

# === Segmentazione rapida ===
section_title("Segmentazione rapida", icon="🧭")

colA, colB = st.columns(2)

with colA:
    st.markdown("**Top generi per volume recensioni**")
    genres_df = get_top_genres(limit=10)
    if genres_df.empty:
        st.caption("N/A (bridge genere non popolato o DW vuoto).")
    else:
        st.bar_chart(genres_df.set_index("genre")[["reviews"]])

with colB:
    st.markdown("**Top lingue**")
    lang_df = get_language_distribution(limit=10)
    if lang_df.empty:
        st.caption("N/A (usertable non popolata o DW vuoto).")
    else:
        st.bar_chart(lang_df.set_index("language")[["n"]])

section_divider()

# === Top games (home) ===
section_title("Top giochi", icon="🏆")
top_games = get_top_games_home(limit=10)
if top_games.empty:
    st.caption("N/A (DW vuoto).")
else:
    st.dataframe(top_games, use_container_width=True, hide_index=True)

section_divider()

# === Dataset in forma sintetica ===
section_title("Dataset principali", icon="🗃️")

datasets = get_datasets_info()
for ds in datasets:
    with st.expander(f"{ds.name} – ~{ds.rows_approx:,} righe"):
        st.write(ds.description)
        st.markdown(
            f"- Righe (circa): **{ds.rows_approx:,}**  \n"
            f"- Colonne (circa): **{ds.columns_approx}**"
        )

render_footer()