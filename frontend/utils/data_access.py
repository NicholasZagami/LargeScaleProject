"""
data_access.py
---------------

Questo modulo rappresenta il *livello logico* di accesso ai dati per il frontend.

Responsabilità:
- definire funzioni ad alto livello usate dalle pagine Streamlit
- incapsulare query SQL specifiche per dashboard e KPI
- fornire fallback (mock) se il database non è disponibile o vuoto

NON deve:
- gestire direttamente connessioni
- sapere come è fatto il database a basso livello

In altre parole:
data_access.py = "quali dati servono alla UI"
"""
from __future__ import annotations

from dataclasses import dataclass
import streamlit as st

from frontend.utils.db import query_df


# =========================
# Dataclass per la UI
# =========================

@dataclass
class KPIs:
    total_games: int
    total_reviews: int
    avg_rating: float


@dataclass
class DatasetInfo:
    name: str
    description: str
    rows_approx: int
    columns_approx: int


# =========================
# Utility interne
# =========================

def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


# =========================
# Funzioni pubbliche
# =========================

@st.cache_data(ttl=60)
def get_kpis() -> KPIs:
    """
    Restituisce i KPI principali per la Home.

    - Se Postgres è disponibile e popolato → KPI reali
    - Altrimenti → valori mock (la UI non si rompe)
    """
    fallback = KPIs(
        total_games=125_000,
        total_reviews=10_500_000,
        avg_rating=4.1,
    )

    try:
        games_df = query_df('SELECT COUNT(*) AS n FROM "public"."game"')
        reviews_df = query_df('SELECT COUNT(*) AS n FROM "public"."review"')

        total_games = _safe_int(games_df.iloc[0]["n"])
        total_reviews = _safe_int(reviews_df.iloc[0]["n"])

        avg_df = query_df(
            'SELECT AVG(review_score) AS avg_rating FROM "public"."game"'
        )
        avg_rating = _safe_float(avg_df.iloc[0]["avg_rating"], fallback.avg_rating)

        if total_games == 0 and total_reviews == 0:
            return fallback

        return KPIs(
            total_games=total_games,
            total_reviews=total_reviews,
            avg_rating=avg_rating,
        )

    except Exception:
        return fallback


@st.cache_data(ttl=120)
def get_datasets_info() -> list[DatasetInfo]:
    """
    Informazioni sintetiche sui dataset usati nelle dashboard.
    Usa Postgres se possibile, altrimenti fallback mock.
    """
    fallback = [
        DatasetInfo(
            name="Games dataset",
            description="Catalogo giochi Steam (dimension Game + bridge).",
            rows_approx=125_000,
            columns_approx=40,
        ),
        DatasetInfo(
            name="Reviews dataset",
            description="Recensioni utenti Steam (fact Review + Date + User).",
            rows_approx=10_500_000,
            columns_approx=25,
        ),
    ]

    try:
        games_rows = query_df('SELECT COUNT(*) AS n FROM "public"."game"').iloc[0]["n"]
        reviews_rows = query_df('SELECT COUNT(*) AS n FROM "public"."review"').iloc[0]["n"]

        games_cols = query_df(
            """
            SELECT COUNT(*) AS n
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='game'
            """
        ).iloc[0]["n"]

        reviews_cols = query_df(
            """
            SELECT COUNT(*) AS n
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='review'
            """
        ).iloc[0]["n"]

        if games_rows == 0 and reviews_rows == 0:
            return fallback

        return [
            DatasetInfo(
                name="Games dataset (Postgres DWH)",
                description=(
                    "Dimensione Game con relazioni M:N "
                    "verso Genre, Category e Publisher."
                ),
                rows_approx=_safe_int(games_rows, fallback[0].rows_approx),
                columns_approx=_safe_int(games_cols, fallback[0].columns_approx),
            ),
            DatasetInfo(
                name="Reviews dataset (Postgres DWH)",
                description=(
                    "Fact table Review collegata a Game, Date e User."
                ),
                rows_approx=_safe_int(reviews_rows, fallback[1].rows_approx),
                columns_approx=_safe_int(reviews_cols, fallback[1].columns_approx),
            ),
        ]

    except Exception:
        return fallback