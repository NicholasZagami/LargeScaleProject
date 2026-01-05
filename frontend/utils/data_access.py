"""
data_access.py
---------------

Livello logico di accesso ai dati per il frontend.

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

@dataclass(frozen=True)
class KPIs:
    total_games: int
    total_reviews: int
    avg_rating: float


@dataclass(frozen=True)
class DatasetInfo:
    name: str
    description: str
    rows_approx: int
    columns_approx: int


# =========================
# Utility interne
# =========================

DWH_SCHEMA = "dwh"  # unico punto da cambiare se in futuro rinominate lo schema


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


def _empty_df():
    return query_df("SELECT 1 WHERE false")


def _table_exists(schema: str, table: str) -> bool:
    df = query_df(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = :schema
          AND table_name = :table
          AND table_type = 'BASE TABLE'
        LIMIT 1
        """,
        {"schema": schema, "table": table},
    )
    return not df.empty


def _dwh_ready() -> bool:
    # pronto se almeno game + review esistono
    return _table_exists(DWH_SCHEMA, "game") and _table_exists(DWH_SCHEMA, "review")


# =========================
# Home: KPI + dataset info
# =========================

@st.cache_data(ttl=60)
def get_kpis() -> KPIs:
    fallback = KPIs(
        total_games=125_000,
        total_reviews=10_500_000,
        avg_rating=4.1,
    )

    try:
        if not _dwh_ready():
            return fallback

        games_df = query_df(f'SELECT COUNT(*) AS n FROM "{DWH_SCHEMA}"."game"')
        reviews_df = query_df(f'SELECT COUNT(*) AS n FROM "{DWH_SCHEMA}"."review"')

        total_games = _safe_int(games_df.iloc[0]["n"])
        total_reviews = _safe_int(reviews_df.iloc[0]["n"])

        if total_games == 0 and total_reviews == 0:
            return fallback

        avg_df = query_df(f'SELECT AVG(review_score) AS avg_score FROM "{DWH_SCHEMA}"."game"')
        avg_score_0_100 = _safe_float(avg_df.iloc[0]["avg_score"], 0.0)

        # 0-100 -> 0-5 stelle
        avg_rating_0_5 = avg_score_0_100 / 20.0 if avg_score_0_100 else fallback.avg_rating

        return KPIs(
            total_games=total_games,
            total_reviews=total_reviews,
            avg_rating=avg_rating_0_5,
        )

    except Exception:
        return fallback


@st.cache_data(ttl=120)
def get_datasets_info() -> list[DatasetInfo]:
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
        if not _dwh_ready():
            return fallback

        games_rows = query_df(f'SELECT COUNT(*) AS n FROM "{DWH_SCHEMA}"."game"').iloc[0]["n"]
        reviews_rows = query_df(f'SELECT COUNT(*) AS n FROM "{DWH_SCHEMA}"."review"').iloc[0]["n"]

        games_cols = query_df(
            """
            SELECT COUNT(*) AS n
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = 'game'
            """,
            {"schema": DWH_SCHEMA},
        ).iloc[0]["n"]

        reviews_cols = query_df(
            """
            SELECT COUNT(*) AS n
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = 'review'
            """,
            {"schema": DWH_SCHEMA},
        ).iloc[0]["n"]

        if games_rows == 0 and reviews_rows == 0:
            return fallback

        return [
            DatasetInfo(
                name="Games dataset (Postgres DWH)",
                description="Dimensione Game con relazioni M:N verso Genre, Category e Publisher.",
                rows_approx=_safe_int(games_rows, fallback[0].rows_approx),
                columns_approx=_safe_int(games_cols, fallback[0].columns_approx),
            ),
            DatasetInfo(
                name="Reviews dataset (Postgres DWH)",
                description="Fact table Review collegata a Game, Date e User.",
                rows_approx=_safe_int(reviews_rows, fallback[1].rows_approx),
                columns_approx=_safe_int(reviews_cols, fallback[1].columns_approx),
            ),
        ]

    except Exception:
        return fallback


# =========================
# Home: trend & segmentazione
# =========================

@st.cache_data(ttl=60)
def get_reviews_trend_daily(days: int = 60):
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "date")):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          make_date(d.year, d.month, d.day) AS day,
          COUNT(*) AS reviews,
          AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
        WHERE make_date(d.year, d.month, d.day) >= (CURRENT_DATE - (:days || ' days')::interval)::date
        GROUP BY 1
        ORDER BY 1
        """,
        {"days": int(days)},
    )


@st.cache_data(ttl=120)
def get_language_distribution(limit: int = 10):
    # dipende da usertable
    if not _table_exists(DWH_SCHEMA, "usertable"):
        return _empty_df()

    return query_df(
        f"""
        SELECT language, COUNT(*) AS n
        FROM "{DWH_SCHEMA}"."usertable"
        WHERE language IS NOT NULL AND language <> ''
        GROUP BY language
        ORDER BY n DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


@st.cache_data(ttl=120)
def get_top_genres(limit: int = 10):
    if not (_table_exists(DWH_SCHEMA, "genre_game") and _table_exists(DWH_SCHEMA, "genre") and _table_exists(DWH_SCHEMA, "review")):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          ge.name AS genre,
          COUNT(*) AS reviews,
          AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."genre_game" gg ON gg.id_game = r.id_game
        JOIN "{DWH_SCHEMA}"."genre" ge ON ge.id_genre = gg.id_genre
        GROUP BY ge.name
        ORDER BY reviews DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


@st.cache_data(ttl=60)
def get_top_games_home(limit: int = 10):
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "game")):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          g.name,
          COUNT(*) AS reviews,
          AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment,
          AVG(r.votes_up)::numeric(10,2) AS avg_votes_up
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."game" g ON g.id_game = r.id_game
        GROUP BY g.name
        ORDER BY reviews DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


# =========================
# Games page helpers
# =========================

@st.cache_data(ttl=120)
def list_genres() -> list[str]:
    if not _table_exists(DWH_SCHEMA, "genre"):
        return []
    df = query_df(f'SELECT name FROM "{DWH_SCHEMA}"."genre" ORDER BY name')
    return df["name"].tolist() if not df.empty else []


@st.cache_data(ttl=120)
def list_publishers() -> list[str]:
    if not _table_exists(DWH_SCHEMA, "publisher"):
        return []
    df = query_df(f'SELECT name FROM "{DWH_SCHEMA}"."publisher" ORDER BY name')
    return df["name"].tolist() if not df.empty else []


@st.cache_data(ttl=120)
def get_date_bounds():
    if not _table_exists(DWH_SCHEMA, "date"):
        return None, None
    df = query_df(
        f"""
        SELECT
          MIN(make_date(year, month, day)) AS min_day,
          MAX(make_date(year, month, day)) AS max_day
        FROM "{DWH_SCHEMA}"."date"
        """
    )
    if df.empty:
        return None, None
    return df.iloc[0]["min_day"], df.iloc[0]["max_day"]


@st.cache_data(ttl=60)
def get_top_games_filtered(
    limit: int = 30,
    min_reviews: int = 0,
    date_from=None,
    date_to=None,
    free_to_play: str = "All",
    required_age: str = "All",
    genre: str = "All",
    publisher: str = "All",
    order_by: str = "reviews",
):
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "game") and _table_exists(DWH_SCHEMA, "date")):
        return _empty_df()

    join_genre = ""
    where_genre = ""
    if genre != "All" and _table_exists(DWH_SCHEMA, "genre_game") and _table_exists(DWH_SCHEMA, "genre"):
        join_genre = f"""
        JOIN "{DWH_SCHEMA}"."genre_game" gg ON gg.id_game = r.id_game
        JOIN "{DWH_SCHEMA}"."genre" ge ON ge.id_genre = gg.id_genre
        """
        where_genre = "AND ge.name = :genre"

    join_pub = ""
    where_pub = ""
    if publisher != "All" and _table_exists(DWH_SCHEMA, "publisher_game") and _table_exists(DWH_SCHEMA, "publisher"):
        join_pub = f"""
        JOIN "{DWH_SCHEMA}"."publisher_game" pg ON pg.id_game = r.id_game
        JOIN "{DWH_SCHEMA}"."publisher" pu ON pu.id_publisher = pg.id_publisher
        """
        where_pub = "AND pu.name = :publisher"

    where_free = ""
    if free_to_play != "All":
        where_free = "AND g.free_to_play = :free_to_play"

    where_age = ""
    if required_age != "All":
        where_age = "AND g.required_age = :required_age"

    where_date = ""
    params = {"limit": int(limit), "min_reviews": int(min_reviews)}

    if date_from is not None:
        where_date += " AND make_date(d.year, d.month, d.day) >= :date_from"
        params["date_from"] = date_from
    if date_to is not None:
        where_date += " AND make_date(d.year, d.month, d.day) <= :date_to"
        params["date_to"] = date_to

    if genre != "All":
        params["genre"] = genre
    if publisher != "All":
        params["publisher"] = publisher
    if free_to_play != "All":
        params["free_to_play"] = (free_to_play == "Yes")
    if required_age != "All":
        params["required_age"] = 18 if required_age == "18+" else 0

    order_map = {
        "reviews": "reviews DESC",
        "avg_sentiment": "avg_sentiment DESC NULLS LAST",
        "avg_votes_up": "avg_votes_up DESC NULLS LAST",
    }
    order_sql = order_map.get(order_by, "reviews DESC")

    sql = f"""
    SELECT
      g.id_game,
      g.name,
      COUNT(*) AS reviews,
      AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment,
      AVG(r.votes_up)::numeric(10,2) AS avg_votes_up,
      BOOL_OR(g.free_to_play) AS free_to_play,
      MAX(g.required_age) AS required_age
    FROM "{DWH_SCHEMA}"."review" r
    JOIN "{DWH_SCHEMA}"."game" g ON g.id_game = r.id_game
    JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
    {join_genre}
    {join_pub}
    WHERE 1=1
      {where_date}
      {where_free}
      {where_age}
      {where_genre}
      {where_pub}
    GROUP BY g.id_game, g.name
    HAVING COUNT(*) >= :min_reviews
    ORDER BY {order_sql}
    LIMIT :limit
    """
    return query_df(sql, params)


@st.cache_data(ttl=60)
def get_game_daily_trend(game_id: int, date_from=None, date_to=None):
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "date")):
        return _empty_df()

    params = {"gid": int(game_id)}
    where_date = ""
    if date_from is not None:
        where_date += " AND make_date(d.year, d.month, d.day) >= :date_from"
        params["date_from"] = date_from
    if date_to is not None:
        where_date += " AND make_date(d.year, d.month, d.day) <= :date_to"
        params["date_to"] = date_to

    sql = f"""
    SELECT
      make_date(d.year, d.month, d.day) AS day,
      COUNT(*) AS reviews,
      AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment
    FROM "{DWH_SCHEMA}"."review" r
    JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
    WHERE r.id_game = :gid
      {where_date}
    GROUP BY 1
    ORDER BY 1
    """
    return query_df(sql, params)


# =========================
# Reviews page helpers
# =========================

@st.cache_data(ttl=60)
def get_reviews_kpis(date_from=None, date_to=None):
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "date")):
        return None

    params = {}
    where_date = ""
    if date_from is not None:
        where_date += " AND make_date(d.year, d.month, d.day) >= :date_from"
        params["date_from"] = date_from
    if date_to is not None:
        where_date += " AND make_date(d.year, d.month, d.day) <= :date_to"
        params["date_to"] = date_to

    df = query_df(
        f"""
        SELECT
          COUNT(*) AS total_reviews,
          AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment,
          AVG(r.votes_up)::numeric(10,2) AS avg_votes_up
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
        WHERE 1=1
          {where_date}
        """,
        params,
    )
    return df.iloc[0] if not df.empty else None


@st.cache_data(ttl=60)
def get_votes_by_sentiment_bins(date_from=None, date_to=None):
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "date")):
        return _empty_df()

    params = {}
    where_date = ""
    if date_from is not None:
        where_date += " AND make_date(d.year, d.month, d.day) >= :date_from"
        params["date_from"] = date_from
    if date_to is not None:
        where_date += " AND make_date(d.year, d.month, d.day) <= :date_to"
        params["date_to"] = date_to

    return query_df(
        f"""
        SELECT
          r.sentiment_round,
          COUNT(*) AS n,
          AVG(r.votes_up)::numeric(10,2) AS avg_votes_up
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
        WHERE 1=1
          {where_date}
        GROUP BY r.sentiment_round
        ORDER BY r.sentiment_round
        """,
        params,
    )


@st.cache_data(ttl=60)
def get_wordcount_bins(date_from=None, date_to=None):
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "date")):
        return _empty_df()

    params = {}
    where_date = ""
    if date_from is not None:
        where_date += " AND make_date(d.year, d.month, d.day) >= :date_from"
        params["date_from"] = date_from
    if date_to is not None:
        where_date += " AND make_date(d.year, d.month, d.day) <= :date_to"
        params["date_to"] = date_to

    return query_df(
        f"""
        SELECT
          CASE
            WHEN r.review_word_count < 50 THEN '<50'
            WHEN r.review_word_count < 100 THEN '50-99'
            WHEN r.review_word_count < 200 THEN '100-199'
            WHEN r.review_word_count < 400 THEN '200-399'
            ELSE '400+'
          END AS wc_bin,
          COUNT(*) AS n,
          AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment,
          MIN(r.review_word_count) AS wc_sort_key
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
        WHERE 1=1
          {where_date}
        GROUP BY wc_bin
        ORDER BY wc_sort_key
        """,
        params,
    )