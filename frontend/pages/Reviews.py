# frontend/pages/Reviews.py
from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from frontend.utils.layout import (
    init_page, render_header, render_sidebar, render_footer,
    section_title, section_divider, kpi_card
)

from frontend.utils.data_access import (
    get_date_bounds,
    get_reviews_kpis,
    get_reviews_trend_period,
    get_rating_histogram,
    get_avg_reviews_per_game,
    get_reviews_per_game_distribution,
    get_votes_by_sentiment_bins,
    get_wordcount_bins,
)

# ------------------------------
# Page setup
# ------------------------------
init_page()
render_header()
render_sidebar()

section_title("Reviews Overview", icon="💬")
st.caption(
    "Questa pagina analizza il comportamento delle recensioni: volume nel tempo, distribuzione del rating, "
    "concentrazione (pochi giochi dominano) e segnali di engagement (votes, sentiment, lunghezza testo)."
)

# ------------------------------
# Filtri globali
# ------------------------------
min_day, max_day = get_date_bounds()

with st.expander("🎛️ Filtri", expanded=True):
    c1, c2 = st.columns([1.8, 1])

    with c1:
        if min_day is None or max_day is None:
            st.caption("Date range: N/A")
            date_from = None
            date_to = None
        else:
            # Streamlit date_input può restituire 1 o 2 valori
            date_range = st.date_input("Date range", value=(min_day, max_day))
            if isinstance(date_range, tuple) and len(date_range) == 2:
                date_from, date_to = date_range
            else:
                date_from, date_to = min_day, max_day

            if date_from and date_to and date_from > date_to:
                st.warning("Date range non valido: la data di inizio è successiva alla data di fine.")
                date_from, date_to = min_day, max_day

    with c2:
        freq = st.selectbox("Granularità trend", ["month", "year"], index=0)

section_divider()

tab_overview, tab_rating, tab_concentration, tab_behavior = st.tabs(
    ["📌 Overview", "⭐ Rating distribution", "📉 Concentration", "🧠 Behavior"]
)

# ------------------------------
# TAB 1 — OVERVIEW
# ------------------------------
with tab_overview:
    kpi = get_reviews_kpis(date_from=date_from, date_to=date_to)
    if kpi is None:
        st.warning("DW non pronto o vuoto: impossibile calcolare KPI.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Recensioni (nel range)", f"{int(kpi['total_reviews']):,}")
        with c2:
            kpi_card("Sentiment medio", f"{float(kpi['avg_sentiment'] or 0):.2f}")
        with c3:
            kpi_card("Votes up medi", f"{float(kpi['avg_votes_up'] or 0):.2f}")

        avg_pg = get_avg_reviews_per_game(date_from=date_from, date_to=date_to)
        with c4:
            if avg_pg is None:
                kpi_card("Reviews per game (mediana)", "N/A")
            else:
                kpi_card("Reviews per game (mediana)", f"{float(avg_pg['median_reviews_per_game'] or 0):.0f}")

    section_divider()

    st.subheader("Volume recensioni nel tempo")
    trend = get_reviews_trend_period(date_from=date_from, date_to=date_to, freq=freq)
    if trend.empty:
        st.info("Trend non disponibile.")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("**Numero recensioni per periodo**")
            st.line_chart(trend.set_index("period")[["reviews"]])
        with right:
            st.markdown("**Sentiment medio per periodo**")
            st.line_chart(trend.set_index("period")[["avg_sentiment"]])

    st.caption(
        "Interpretazione: il trend evidenzia stagionalità e cambiamenti nel sentiment medio nel tempo. "
        "Il range selezionato sopra filtra KPI e trend."
    )

# ------------------------------
# TAB 2 — RATING DISTRIBUTION
# ------------------------------
with tab_rating:
    st.subheader("Distribuzione del rating (review_score dei giochi)")
    st.caption("Distribuzione del punteggio 1–9 associato ai giochi (dimensione `game`).")

    hist = get_rating_histogram()
    if hist.empty:
        st.info("Distribuzione rating non disponibile (manca `game.review_score`?).")
    else:
        st.bar_chart(hist.set_index("score_bin")[["n"]])
        st.caption(
            "Interpretazione: mostra la qualità percepita del catalogo (rating 1–9). "
            "Utile per osservare skew, outlier e concentrazione in fasce."
        )

# ------------------------------
# TAB 3 — CONCENTRATION / LONG TAIL
# ------------------------------
with tab_concentration:
    st.subheader("Engagement non uniforme: long tail delle recensioni per gioco")
    st.caption(
        "Obiettivo: mostrare che l'engagement non è distribuito uniformemente: pochi giochi concentrano moltissime recensioni."
    )

    per_game = get_reviews_per_game_distribution()
    if per_game.empty:
        st.info("Non disponibile (manca `review`).")
    else:
        # Aspettato: colonne come [id_game, name?, reviews]
        # Se non è già ordinato, forziamo ordine decrescente per coerenza.
        if "reviews" in per_game.columns:
            per_game = per_game.sort_values("reviews", ascending=False).reset_index(drop=True)

        total_reviews = int(per_game["reviews"].sum()) if "reviews" in per_game.columns else 0
        n_games = int(per_game.shape[0])

        top10_share = (per_game.head(10)["reviews"].sum() / total_reviews) if total_reviews else 0
        top100_share = (per_game.head(100)["reviews"].sum() / total_reviews) if total_reviews else 0

        a, b, c = st.columns(3)
        a.metric("Giochi con ≥1 review", f"{n_games:,}")
        b.metric("Quota reviews Top 10 giochi", f"{top10_share * 100:.1f}%")
        c.metric("Quota reviews Top 100 giochi", f"{top100_share * 100:.1f}%")

        section_divider()

        st.markdown("**Curva rank → numero recensioni (power-law / long tail)**")
        ranked = per_game.copy()
        ranked["rank"] = ranked.index + 1
        st.line_chart(ranked.set_index("rank")[["reviews"]])

        st.caption(
            "Interpretazione: una discesa rapida indica un comportamento heavy-tailed (long tail), "
            "tipico dei marketplace digitali."
        )

        section_divider()

        st.markdown("**Top giochi per numero di recensioni**")
        show_cols = [c for c in ["id_game", "name", "reviews"] if c in per_game.columns]
        st.dataframe(per_game[show_cols].head(20), use_container_width=True, hide_index=True)

# ------------------------------
# TAB 4 — BEHAVIOR (votes/sentiment/wordcount)
# ------------------------------
with tab_behavior:
    st.subheader("Engagement vs Sentiment")
    st.caption("Relazione tra sentiment e segnali di engagement (votes).")

    vs = get_votes_by_sentiment_bins(date_from=date_from, date_to=date_to)
    if vs.empty:
        st.info("N/A (mancano colonne o dati nel range selezionato).")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Numero recensioni per sentiment**")
            st.bar_chart(vs.set_index("sentiment_round")[["n"]])
        with c2:
            st.markdown("**Votes up medi per sentiment**")
            st.line_chart(vs.set_index("sentiment_round")[["avg_votes_up"]])

        st.caption(
            "Interpretazione: se i votes crescono con sentiment più alto, suggerisce che review positive "
            "tendono a ricevere più approvazione (ma dipende da community e contenuto)."
        )

    section_divider()

    st.subheader("Lunghezza testo e sentiment")
    st.caption("Distribuzione della lunghezza delle recensioni e come varia il sentiment medio.")

    wc = get_wordcount_bins(date_from=date_from, date_to=date_to)
    if wc.empty:
        st.info("N/A (mancano colonne o dati nel range selezionato).")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Distribuzione lunghezza recensioni**")
            st.bar_chart(wc.set_index("wc_bin")[["n"]])
        with c2:
            st.markdown("**Sentiment medio per lunghezza**")
            st.line_chart(wc.set_index("wc_bin")[["avg_sentiment"]])

        st.caption(
            "Interpretazione: review molto corte possono essere più estreme (solo 'Great!' o 'Bad!'), "
            "mentre review più lunghe talvolta contengono giudizi più articolati."
        )

render_footer()