# frontend/pages/Games.py
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
    # overview
    get_games_overview_kpis,
    get_releases_over_time,
    get_games_by_genre,
    get_games_by_publisher,
    get_price_buckets,
    get_price_vs_rating,

    # prices / level-2
    get_free_vs_paid_rating,
    get_price_bucket_vs_rating,

    # market structure / level-2
    get_genre_engagement,
    get_publisher_quality_quantity,
    get_top_publishers_by_rating,

    # explorer
    list_genres,
    list_publishers,
    get_date_bounds,
    get_top_games_filtered,
    get_game_daily_trend,
)

# ------------------------------
# Page setup
# ------------------------------
init_page()
render_header()
render_sidebar()

section_title("Games Overview", icon="🎮")
st.caption(
    "Vista ad alto livello del catalogo Steam: dimensione, struttura (generi/publisher), prezzi e dinamiche nel tempo. "
    "In fondo trovi anche l'Explorer con drill-down."
)

tab_overview, tab_prices, tab_structure, tab_explorer = st.tabs(
    ["📌 Overview", "💶 Prices", "🏢 Market structure", "🔎 Explorer"]
)

# ------------------------------
# TAB 1 — OVERVIEW
# ------------------------------
with tab_overview:
    row = get_games_overview_kpis()
    if row is None:
        st.warning("DW non disponibile o tabella `game` mancante.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Giochi nel catalogo", f"{int(row['total_games']):,}")
        with c2:
            kpi_card("Free-to-play", f"{int(row['free_games']):,}")
        with c3:
            kpi_card("Paid games", f"{int(row['paid_games']):,}")
        with c4:
            # review_score 0-9 → 0-5 stelle
            avg_score = float(row["avg_score_0_100"]) if row["avg_score_0_100"] is not None else 0.0
            kpi_card("Rating medio", f"{avg_score * 5 / 9:.2f} ⭐")

    section_divider()

    st.subheader("Rilasci nel tempo")
    rel = get_releases_over_time(freq="month")
    if rel.empty:
        st.info("Non ho abbastanza dati per mostrare i rilasci nel tempo (manca `release_date`?).")
    else:
        st.line_chart(rel.set_index("period")[["games"]])

    st.caption(
        "Interpretazione: la serie temporale dei rilasci aiuta a capire crescita/stasi del catalogo e possibili cicli."
    )

# ------------------------------
# TAB 2 — PRICES
# ------------------------------
with tab_prices:
    st.subheader("Prezzi e qualità percepita")

    left, right = st.columns([1.2, 1])

    with left:
        st.markdown("**Distribuzione prezzi (fasce)**")
        buckets = get_price_buckets()
        if buckets.empty:
            st.info("La colonna `price` non è disponibile nel vostro DW (o è vuota).")
        else:
            st.bar_chart(buckets.set_index("bucket")[["n"]])
            st.caption("Interpretazione: evidenzia la presenza di free-to-play e la concentrazione in fasce low/mid/high.")

    with right:
        st.markdown("**Free vs Paid (rating medio)**")
        seg = get_free_vs_paid_rating()
        if seg.empty:
            st.info("Non disponibile (mancano `free_to_play` / `review_score`).")
        else:
            tmp = seg.copy()
            tmp["avg_rating_0_5"] = tmp["avg_score_0_100"].astype(float) * 5 / 9
            st.bar_chart(tmp.set_index("segment")[["avg_rating_0_5"]])
            st.caption("Confronto diretto tra qualità percepita dei giochi free-to-play e paid.")

    section_divider()

    st.markdown("### Prezzo vs Rating (scatter)")
    scatter = get_price_vs_rating(sample_limit=20000)
    if scatter.empty:
        st.info("Non posso mostrare prezzo vs rating (mancano `price` o `review_score`).")
    else:
        st.caption("Campione per mantenere la pagina veloce (ogni punto = un gioco).")
        st.scatter_chart(scatter, x="price", y="review_score")
        st.caption("Interpretazione: aiuta a capire se esiste una relazione (anche debole) tra prezzo e soddisfazione.")

    section_divider()

    st.markdown("### Rating medio per fascia prezzo")
    br = get_price_bucket_vs_rating()
    if br.empty:
        st.info("Non disponibile (manca `price` o `review_score`).")
    else:
        tmp = br.copy()
        tmp["avg_rating_0_5"] = tmp["avg_score_0_100"].astype(float) * 5 / 9
        st.bar_chart(tmp.set_index("bucket")[["avg_rating_0_5"]])
        st.caption("Interpretazione: fasce prezzo diverse possono avere rating simili → prezzo ≠ qualità.")

# ------------------------------
# TAB 3 — MARKET STRUCTURE
# ------------------------------
with tab_structure:
    st.subheader("Struttura del mercato (catalogo)")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Giochi per genere (Top)**")
        g = get_games_by_genre(limit=15)
        if g.empty:
            st.info("Tabelle genre/genre_game non disponibili o vuote.")
        else:
            st.bar_chart(g.set_index("genre")[["games"]])

    with c2:
        st.markdown("**Giochi per publisher (Top)**")
        p = get_games_by_publisher(limit=15)
        if p.empty:
            st.info("Tabelle publisher/publisher_game non disponibili o vuote.")
        else:
            st.bar_chart(p.set_index("publisher")[["games"]])

    section_divider()

    st.subheader("Genere vs Engagement (recensioni per gioco + rating)")
    ge = get_genre_engagement(limit=15)
    if ge.empty:
        st.info("Non disponibile (servono join tra review ↔ game ↔ genre).")
    else:
        a, b = st.columns(2)
        with a:
            st.markdown("**Reviews per game (Top generi)**")
            st.bar_chart(ge.set_index("genre")[["reviews_per_game"]])
            st.caption("Interpretazione: quantifica quali generi generano più engagement medio per titolo.")

        with b:
            st.markdown("**Rating medio per genere**")
            tmp = ge.copy()
            tmp["avg_rating_0_5"] = tmp["avg_score_0_100"].astype(float) * 5 / 9
            st.bar_chart(tmp.set_index("genre")[["avg_rating_0_5"]])
            st.caption("Interpretazione: mostra differenze di qualità percepita tra community di generi diversi.")

    section_divider()

    st.subheader("Publisher: qualità vs quantità (scatter)")
    pub = get_publisher_quality_quantity(limit=300)
    if pub.empty:
        st.info("Non disponibile (servono join publisher ↔ game ↔ review).")
    else:
        st.caption("Ogni punto è un publisher (filtrati: publisher con almeno 2 giochi).")
        st.scatter_chart(pub, x="games", y="avg_score_0_100")
        st.caption("Interpretazione: confronta publisher prolifici vs rating medio (qualità ≠ quantità).")

        section_divider()

        st.subheader("Top publisher per rating (min giochi)")
        cA, cB = st.columns([1, 2])
        with cA:
            min_games = st.number_input("Min giochi per publisher", min_value=2, value=5, step=1)
        with cB:
            top_lim = st.slider("Top N", min_value=5, max_value=30, value=15, step=5)

        top_pub = get_top_publishers_by_rating(limit=int(top_lim), min_games=int(min_games))
        if top_pub.empty:
            st.info("Non disponibile o filtri troppo restrittivi.")
        else:
            tmp = top_pub.copy()
            tmp["avg_rating_0_5"] = tmp["avg_score_0_100"].astype(float) * 5 / 9
            st.bar_chart(tmp.set_index("publisher")[["avg_rating_0_5"]])
            st.caption("Interpretazione: evidenzia publisher consistenti (rating alto su più titoli).")

    section_divider()

    st.subheader("Lettura guidata (per chi non conosce il progetto)")
    st.markdown(
        "- **Concentrazione del catalogo**: pochi publisher/genere possono avere tantissimi titoli.\n"
        "- **Engagement**: alcuni generi generano più recensioni per gioco (mainstream vs nicchie).\n"
        "- **Strategia publisher**: mettere molti titoli non implica rating alto — utile per discutere qualità vs quantità.\n"
    )

# ------------------------------
# TAB 4 — EXPLORER (top + drilldown)
# ------------------------------
with tab_explorer:
    st.subheader("Explorer: Top games + drill-down")
    st.caption("Sezione interattiva per analisi mirate: filtri + selezione gioco + trend temporale.")

    min_day, max_day = get_date_bounds()

    with st.expander("🎛️ Filtri", expanded=True):
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 1])
        with c1:
            top_n = st.slider("Top N", 10, 200, 30, 10)
        with c2:
            min_reviews = st.number_input("Min recensioni", min_value=0, value=50, step=50)
        with c3:
            order_by = st.selectbox("Ordina per", ["reviews", "avg_sentiment", "avg_votes_up"], index=0)
        with c4:
            free_to_play = st.selectbox("Free-to-play", ["All", "Yes", "No"], index=0)

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
        st.info("Nessun risultato: prova a ridurre i filtri (Min recensioni = 0, Genre/Publisher = All).")
    else:
        st.markdown("#### Top games (filtrati)")
        st.dataframe(df, use_container_width=True, hide_index=True)

        section_divider()

        st.markdown("#### Drill-down: trend del gioco selezionato")
        df_choice = df[["id_game", "name"]].copy()
        df_choice["label"] = df_choice["name"].astype(str) + "  (id=" + df_choice["id_game"].astype(str) + ")"
        selected_label = st.selectbox("Seleziona gioco", df_choice["label"].tolist(), index=0)
        selected_id = df_choice.loc[df_choice["label"] == selected_label, "id_game"].iloc[0]

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