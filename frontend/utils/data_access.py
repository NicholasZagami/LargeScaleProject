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
def get_game_daily_trend(game_id, date_from=None, date_to=None):
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "date")):
        return _empty_df()

    params = {"gid": str(game_id)}  # <-- sempre stringa
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

def _column_exists(schema: str, table: str, column: str) -> bool:
    df = query_df(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = :table
          AND column_name = :column
        LIMIT 1
        """,
        {"schema": schema, "table": table, "column": column},
    )
    return not df.empty

@st.cache_data(ttl=120)
def get_games_overview_kpis():
    if not _table_exists(DWH_SCHEMA, "game"):
        return None

    has_price = _column_exists(DWH_SCHEMA, "game", "price")

    sql = f"""
    SELECT
      COUNT(*) AS total_games,
      SUM(CASE WHEN free_to_play IS TRUE THEN 1 ELSE 0 END) AS free_games,
      SUM(CASE WHEN free_to_play IS FALSE THEN 1 ELSE 0 END) AS paid_games,
      AVG(review_score)::numeric(10,2) AS avg_score_0_100
      {", AVG(price)::numeric(10,2) AS avg_price" if has_price else ""}
    FROM "{DWH_SCHEMA}"."game"
    """
    df = query_df(sql)
    return df.iloc[0] if not df.empty else None

@st.cache_data(ttl=120)
def get_price_buckets():
    if not _table_exists(DWH_SCHEMA, "game") or not _column_exists(DWH_SCHEMA, "game", "price"):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          CASE
            WHEN price = 0 THEN 'Free'
            WHEN price < 5 THEN 'Low (<5)'
            WHEN price < 15 THEN 'Mid (5-14.99)'
            WHEN price < 30 THEN 'High (15-29.99)'
            ELSE 'Premium (>=30)'
          END AS bucket,
          COUNT(*) AS n
        FROM "{DWH_SCHEMA}"."game"
        GROUP BY 1
        ORDER BY
          CASE bucket
            WHEN 'Free' THEN 1
            WHEN 'Low (<5)' THEN 2
            WHEN 'Mid (5-14.99)' THEN 3
            WHEN 'High (15-29.99)' THEN 4
            ELSE 5
          END
        """
    )

@st.cache_data(ttl=120)
def get_games_by_genre(limit: int = 15):
    if not (_table_exists(DWH_SCHEMA, "genre_game") and _table_exists(DWH_SCHEMA, "genre")):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          ge.name AS genre,
          COUNT(DISTINCT gg.id_game) AS games
        FROM "{DWH_SCHEMA}"."genre_game" gg
        JOIN "{DWH_SCHEMA}"."genre" ge ON ge.id_genre = gg.id_genre
        GROUP BY ge.name
        ORDER BY games DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )

@st.cache_data(ttl=120)
def get_games_by_publisher(limit: int = 15):
    if not (_table_exists(DWH_SCHEMA, "publisher_game") and _table_exists(DWH_SCHEMA, "publisher")):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          pu.name AS publisher,
          COUNT(DISTINCT pg.id_game) AS games
        FROM "{DWH_SCHEMA}"."publisher_game" pg
        JOIN "{DWH_SCHEMA}"."publisher" pu ON pu.id_publisher = pg.id_publisher
        GROUP BY pu.name
        ORDER BY games DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )

@st.cache_data(ttl=120)
def get_releases_over_time(freq: str = "month"):
    if not _table_exists(DWH_SCHEMA, "game") or not _column_exists(DWH_SCHEMA, "game", "release_date"):
        return _empty_df()

    if freq == "year":
        trunc = "year"
    else:
        trunc = "month"

    return query_df(
        f"""
        SELECT
          date_trunc('{trunc}', TO_DATE(release_date, 'DD Mon, YYYY'))::date AS period,
          COUNT(*) AS games
        FROM "{DWH_SCHEMA}"."game"
        WHERE release_date IS NOT NULL
          AND release_date NOT ILIKE '%coming soon%'
          AND release_date NOT ILIKE '%to be announced%'
          AND release_date ~ '^[0-9]{{1,2}} [A-Za-z]{{3}}, [0-9]{{4}}$'
        GROUP BY 1
        ORDER BY 1
        """
    )

@st.cache_data(ttl=120)
def get_price_vs_rating(sample_limit: int = 20000):
    if not _table_exists(DWH_SCHEMA, "game"):
        return _empty_df()
    if not (_column_exists(DWH_SCHEMA, "game", "price") and _column_exists(DWH_SCHEMA, "game", "review_score")):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          price,
          review_score
        FROM "{DWH_SCHEMA}"."game"
        WHERE price IS NOT NULL
          AND review_score IS NOT NULL
        ORDER BY random()
        LIMIT :limit
        """,
        {"limit": int(sample_limit)},
    )

@st.cache_data(ttl=120)
def get_reviews_trend_period(date_from=None, date_to=None, freq: str = "month"):
    """
    freq: 'month' oppure 'year'
    """
    if not (_table_exists(DWH_SCHEMA, "review") and _table_exists(DWH_SCHEMA, "date")):
        return _empty_df()

    trunc = "year" if freq == "year" else "month"

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
          date_trunc('{trunc}', make_date(d.year, d.month, d.day))::date AS period,
          COUNT(*) AS reviews,
          AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment,
          AVG(r.votes_up)::numeric(10,2) AS avg_votes_up
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
        WHERE 1=1
          {where_date}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    )

@st.cache_data(ttl=120)
def get_rating_histogram(bin_size: int = 10):
    if not _table_exists(DWH_SCHEMA, "game"):
        return _empty_df()

    # review_score: 0-100
    return query_df(
        f"""
        SELECT
          (review_score / :bin_size) * :bin_size AS score_bin,
          COUNT(*) AS n
        FROM "{DWH_SCHEMA}"."game"
        WHERE review_score IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        """,
        {"bin_size": int(bin_size)},
    )

@st.cache_data(ttl=120)
def get_reviews_per_game_distribution(limit_games: int = 200000):
    """
    Ritorna la distribuzione: per ogni gioco quante recensioni ha.
    Utile per long tail / power-law.
    """
    if not _table_exists(DWH_SCHEMA, "review"):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          id_game,
          COUNT(*) AS reviews
        FROM "{DWH_SCHEMA}"."review"
        GROUP BY id_game
        ORDER BY reviews DESC
        LIMIT :lim
        """,
        {"lim": int(limit_games)},
    )

@st.cache_data(ttl=120)
def get_avg_reviews_per_game(date_from=None, date_to=None):
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
        WITH per_game AS (
          SELECT r.id_game, COUNT(*) AS reviews
          FROM "{DWH_SCHEMA}"."review" r
          JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
          WHERE 1=1
            {where_date}
          GROUP BY r.id_game
        )
        SELECT
          AVG(reviews)::numeric(12,2) AS avg_reviews_per_game,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY reviews) AS median_reviews_per_game
        FROM per_game
        """,
        params,
    )
    return df.iloc[0] if not df.empty else None

# =========================
# Extra helpers (robusti)
# =========================

def _column_exists(schema: str, table: str, column: str) -> bool:
    df = query_df(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = :table
          AND column_name = :col
        LIMIT 1
        """,
        {"schema": schema, "table": table, "col": column},
    )
    return not df.empty


def _has_columns(schema: str, table: str, cols: list[str]) -> bool:
    return all(_column_exists(schema, table, c) for c in cols)


# =========================
# Games — Prices & Quality
# =========================

@st.cache_data(ttl=120)
def get_free_vs_paid_rating():
    """
    Confronto Free-to-play vs Paid: numero giochi + rating medio.
    Richiede game.free_to_play + game.review_score
    """
    if not _table_exists(DWH_SCHEMA, "game"):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "game", ["free_to_play", "review_score"]):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          CASE WHEN free_to_play THEN 'Free-to-play' ELSE 'Paid' END AS segment,
          COUNT(*) AS games,
          AVG(review_score)::numeric(10,2) AS avg_score_0_100
        FROM "{DWH_SCHEMA}"."game"
        GROUP BY 1
        ORDER BY 1
        """
    )


@st.cache_data(ttl=120)
def get_price_bucket_vs_rating():
    """
    Rating medio per fascia prezzo. (Se nel DW esiste game.price)
    """
    if not _table_exists(DWH_SCHEMA, "game"):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "game", ["price", "review_score"]):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          CASE
            WHEN price IS NULL THEN 'Unknown'
            WHEN price = 0 THEN 'Free'
            WHEN price < 5 THEN 'Low (<5)'
            WHEN price < 20 THEN 'Mid (5-19.99)'
            ELSE 'High (>=20)'
          END AS bucket,
          COUNT(*) AS games,
          AVG(review_score)::numeric(10,2) AS avg_score_0_100,
          MIN(price) AS sort_key
        FROM "{DWH_SCHEMA}"."game"
        GROUP BY 1
        ORDER BY sort_key NULLS LAST
        """
    )


# =========================
# Games — Genre engagement
# =========================

@st.cache_data(ttl=120)
def get_genre_engagement(limit: int = 15):
    """
    Per genere:
    - #games
    - #reviews totali
    - reviews per game (media)
    - rating medio giochi del genere
    Richiede: genre, genre_game, game, review (review.id_game può essere TEXT)
    """
    needed_tables = ["genre", "genre_game", "game", "review"]
    if not all(_table_exists(DWH_SCHEMA, t) for t in needed_tables):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "game", ["review_score"]):
        return _empty_df()

    return query_df(
        f"""
        WITH reviews_by_game AS (
          SELECT
            r.id_game,
            COUNT(*) AS reviews
          FROM "{DWH_SCHEMA}"."review" r
          WHERE r.id_game IS NOT NULL
          GROUP BY 1
        )
        SELECT
          ge.name AS genre,
          COUNT(DISTINCT gg.id_game) AS games,
          COALESCE(SUM(rbg.reviews), 0) AS total_reviews,
          (COALESCE(SUM(rbg.reviews), 0)::numeric / NULLIF(COUNT(DISTINCT gg.id_game), 0))::numeric(12,2) AS reviews_per_game,
          AVG(g.review_score)::numeric(10,2) AS avg_score_0_100
        FROM "{DWH_SCHEMA}"."genre_game" gg
        JOIN "{DWH_SCHEMA}"."genre" ge ON ge.id_genre = gg.id_genre
        JOIN "{DWH_SCHEMA}"."game" g ON g.id_game = gg.id_game
        LEFT JOIN reviews_by_game rbg ON rbg.id_game = gg.id_game
        GROUP BY ge.name
        ORDER BY total_reviews DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


# =========================
# Games — Publisher analysis (quality vs quantity)
# =========================

@st.cache_data(ttl=120)
def get_publisher_quality_quantity(limit: int = 200):
    """
    Per publisher:
    - games count
    - rating medio
    - reviews totali (proxy di successo/engagement)
    Richiede: publisher, publisher_game, game, review
    """
    needed_tables = ["publisher", "publisher_game", "game", "review"]
    if not all(_table_exists(DWH_SCHEMA, t) for t in needed_tables):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "game", ["review_score"]):
        return _empty_df()

    return query_df(
        f"""
        WITH reviews_by_game AS (
          SELECT
            r.id_game,
            COUNT(*) AS reviews
          FROM "{DWH_SCHEMA}"."review" r
          WHERE r.id_game IS NOT NULL
          GROUP BY 1
        )
        SELECT
          pu.name AS publisher,
          COUNT(DISTINCT pg.id_game) AS games,
          AVG(g.review_score)::numeric(10,2) AS avg_score_0_100,
          COALESCE(SUM(rbg.reviews), 0) AS total_reviews
        FROM "{DWH_SCHEMA}"."publisher_game" pg
        JOIN "{DWH_SCHEMA}"."publisher" pu ON pu.id_publisher = pg.id_publisher
        JOIN "{DWH_SCHEMA}"."game" g ON g.id_game = pg.id_game
        LEFT JOIN reviews_by_game rbg ON rbg.id_game = pg.id_game
        GROUP BY pu.name
        HAVING COUNT(DISTINCT pg.id_game) >= 2
        ORDER BY total_reviews DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


@st.cache_data(ttl=120)
def get_top_publishers_by_rating(limit: int = 15, min_games: int = 5):
    """
    Top publisher per rating medio (filtrando publisher con pochi giochi).
    """
    if not all(_table_exists(DWH_SCHEMA, t) for t in ["publisher", "publisher_game", "game"]):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "game", ["review_score"]):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          pu.name AS publisher,
          COUNT(*) AS games,
          AVG(g.review_score)::numeric(10,2) AS avg_score_0_100
        FROM "{DWH_SCHEMA}"."publisher_game" pg
        JOIN "{DWH_SCHEMA}"."publisher" pu ON pu.id_publisher = pg.id_publisher
        JOIN "{DWH_SCHEMA}"."game" g ON g.id_game = pg.id_game
        GROUP BY pu.name
        HAVING COUNT(*) >= :min_games
        ORDER BY avg_score_0_100 DESC NULLS LAST
        LIMIT :limit
        """,
        {"limit": int(limit), "min_games": int(min_games)},
    )


# =========================
# Reviews — Sentiment vs Rating / by Genre
# =========================

@st.cache_data(ttl=120)
def get_sentiment_vs_rating_per_game(limit: int = 20000):
    """
    Per gioco: rating (game.review_score) vs sentiment medio (review.sentiment_round)
    Utile come scatter.
    """
    if not all(_table_exists(DWH_SCHEMA, t) for t in ["review", "game"]):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "review", ["sentiment_round", "id_game"]):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "game", ["review_score"]):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          g.id_game,
          g.review_score,
          AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment,
          COUNT(*) AS reviews
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."game" g
          ON r.id_game = g.id_game
        GROUP BY g.id_game, g.review_score
        HAVING COUNT(*) >= 5
        ORDER BY reviews DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


@st.cache_data(ttl=120)
def get_sentiment_by_genre(limit: int = 15):
    """
    Sentiment medio per genere + volume recensioni.
    """
    needed_tables = ["review", "genre_game", "genre", "game"]
    if not all(_table_exists(DWH_SCHEMA, t) for t in needed_tables):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "review", ["sentiment_round", "id_game"]):
        return _empty_df()

    return query_df(
        f"""
        SELECT
          ge.name AS genre,
          COUNT(*) AS reviews,
          AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment
        FROM "{DWH_SCHEMA}"."review" r
        JOIN "{DWH_SCHEMA}"."game" g
          ON r.id_game = g.id_game
        JOIN "{DWH_SCHEMA}"."genre_game" gg ON gg.id_game = g.id_game
        JOIN "{DWH_SCHEMA}"."genre" ge ON ge.id_genre = gg.id_genre
        GROUP BY ge.name
        ORDER BY reviews DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


@st.cache_data(ttl=120)
def get_early_vs_late_sentiment(days_window: int = 90):
    """
    Confronto globale Early vs Late:
    - early = primi N giorni del dataset
    - late  = ultimi N giorni del dataset
    Richiede date + review.sentiment_round
    """
    if not all(_table_exists(DWH_SCHEMA, t) for t in ["review", "date"]):
        return _empty_df()
    if not _has_columns(DWH_SCHEMA, "review", ["sentiment_round", "id_date"]):
        return _empty_df()

    return query_df(
        f"""
        WITH bounds AS (
          SELECT
            MIN(make_date(year, month, day)) AS min_day,
            MAX(make_date(year, month, day)) AS max_day
          FROM "{DWH_SCHEMA}"."date"
        ),
        tagged AS (
          SELECT
            CASE
              WHEN make_date(d.year, d.month, d.day) <= (b.min_day + (:win || ' days')::interval)::date THEN 'Early'
              WHEN make_date(d.year, d.month, d.day) >= (b.max_day - (:win || ' days')::interval)::date THEN 'Late'
              ELSE 'Middle'
            END AS phase,
            r.sentiment_round
          FROM "{DWH_SCHEMA}"."review" r
          JOIN "{DWH_SCHEMA}"."date" d ON d.id_date = r.id_date
          CROSS JOIN bounds b
          WHERE r.sentiment_round IS NOT NULL
        )
        SELECT
          phase,
          COUNT(*) AS reviews,
          AVG(sentiment_round)::numeric(10,2) AS avg_sentiment
        FROM tagged
        WHERE phase IN ('Early', 'Late')
        GROUP BY phase
        ORDER BY phase
        """,
        {"win": int(days_window)},
    )