# frontend/utils/layout.py
from __future__ import annotations

import streamlit as st
from pathlib import Path

APP_TITLE = "Steam Games Data Warehouse"
APP_SUBTITLE = "Catalogo giochi & recensioni Steam"

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"


def init_page():
    """Configura la pagina (titolo, icona, layout) e inietta un po' di CSS."""
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🎮",
        layout="wide",
    )
    _inject_css()


def _inject_css():
    """Stili globali molto leggeri per rendere tutto più pulito."""
    st.markdown(
        """
        <style>
        /* Riduce un po' il padding laterale */
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }

        /* Titolo principale più evidente ma non enorme */
        h2 {
            margin-bottom: 0.2rem;
        }

        /* Card "KPI" */
        .kpi-card {
            padding: 1rem 1.2rem;
            border-radius: 0.8rem;
            background-color: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        /* Sezione separata da una linea morbida */
        .section-divider {
            margin: 1.8rem 0 1rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    """Header compatto con (eventuale) logo e titolo centrali."""
    col_logo, col_title, col_empty = st.columns([1, 3, 1])

    with col_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=56)
        else:
            st.markdown("## 🎮")

    with col_title:
        st.markdown(f"## {APP_TITLE}")
        st.caption(APP_SUBTITLE)


def render_sidebar():
    """Sidebar minimale: solo navigazione + un piccolo box info."""
    with st.sidebar:
        st.markdown("### Navigazione")
        st.markdown("🏠 Home")
        st.markdown("🎮 Giochi")
        st.markdown("💬 Recensioni")

        st.markdown("---")
        st.caption(
            "Dashboard progettata per l'esame di\n"
            "**Large Scale Data Management**.\n\n"
            "I filtri globali e le altre pagine\n"
            "verranno aggiunti nelle prossime iterazioni."
        )


def kpi_card(label: str, value: str, help_text: str | None = None):
    """KPI in una piccola 'card' personalizzata."""
    with st.container():
        st.markdown('<div class="kpi-card">', unsafe_allow_html=True)
        st.metric(label=label, value=value, help=help_text)
        st.markdown("</div>", unsafe_allow_html=True)


def section_divider():
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


def section_title(title: str, icon: str = "📊"):
    st.markdown(f"### {icon} {title}")


def render_footer():
    st.markdown("---")
    st.caption("👨‍🎓 Progetto d'esame – Steam Games Data Warehouse")