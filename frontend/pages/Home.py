# frontend/pages/Home.py
from __future__ import annotations

from pathlib import Path
import sys

# === Fix path per importare 'frontend' ===
ROOT_DIR = Path(__file__).resolve().parents[2]
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
from frontend.utils.data_access import get_kpis, get_datasets_info

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

    # Immagine principale larga
    if hero_img.exists():
        st.image(str(hero_img))
    else:
        st.markdown(
            "<h1 style='text-align:center;'>🎮</h1>",
            unsafe_allow_html=True,
        )

    # Titolo e sottotitolo centrati
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

section_divider()

# === Roadmap compatta ===
section_title("Prossimi passi della dashboard", icon="🗺️")

with st.expander("Mostra roadmap dettagliata"):
    st.markdown(
        """
        1. **Collegamento ai dati reali**
           - integrazione con il data warehouse
           - sostituzione dei valori mock con query reali.

        2. **Nuove pagine**
           - *Games Overview*: prezzi, generi, publisher, trend temporali  
           - *Reviews Overview*: volumi, rating, sentiment.

        3. **Filtri globali**
           - intervallo temporale
           - genere del gioco, publisher, fascia di prezzo
           - confronto tra giochi specifici.

        4. **Performance**
           - caching delle query,
           - pre-aggregazioni lato DW,
           - caricamento asincrono dei grafici più pesanti.
        """
    )

render_footer()