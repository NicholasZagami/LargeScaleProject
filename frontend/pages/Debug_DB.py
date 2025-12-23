from __future__ import annotations

from pathlib import Path
import sys

# Fix import path (come nelle altre pagine)
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from sqlalchemy import text

from frontend.utils.layout import init_page, render_header, render_sidebar, render_footer
from frontend.utils.db import get_engine, query_df

# ------------------------------
# Page setup
# ------------------------------
init_page()
render_header()
render_sidebar()

st.title("🛠️ Debug DB (Postgres)")
st.caption("Pagina di diagnostica: connessione, schemi, tabelle, preview, conteggi e query rapide.")

# ------------------------------
# 1) Test connessione
# ------------------------------
st.subheader("1) Connessione")

try:
    eng = get_engine()
    with eng.connect() as conn:
        db_info = conn.execute(
            text("SELECT current_database() AS db, current_user AS usr, inet_server_addr() AS addr, inet_server_port() AS port")
        ).fetchone()
    st.success(f"✅ Connesso a Postgres | DB: {db_info.db} | User: {db_info.usr} | Server: {db_info.addr}:{db_info.port}")
except Exception as e:
    st.error("❌ Connessione fallita. Controlla POSTGRES_CONNECTION_STRING nel .env")
    st.exception(e)
    st.stop()

st.markdown("---")

# ------------------------------
# 2) Schemi disponibili
# ------------------------------
st.subheader("2) Schemi disponibili")

try:
    schemas_df = query_df(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schema_name
        """
    )
    schemas = schemas_df["schema_name"].tolist()
except Exception as e:
    st.error("Errore nel recupero degli schemi")
    st.exception(e)
    st.stop()

if not schemas:
    st.warning("Nessuno schema trovato (strano).")
    st.stop()

default_schema = "public" if "public" in schemas else schemas[0]
schema = st.selectbox("Schema", schemas, index=schemas.index(default_schema))

# Hint utile: se sei nel DB prefect e vedi solo tabelle Prefect
if schema == "public":
    st.info(
        "ℹ️ Se vedi tabelle come `agent`, `artifact`, `automation` ecc., "
        "probabilmente sei nel DB di Prefect. "
        "Il DW consigliato è in uno schema dedicato (es. `dwh`)."
    )

st.markdown("---")

# ------------------------------
# 3) Lista tabelle
# ------------------------------
st.subheader("3) Tabelle disponibili")

tables_df = query_df(
    """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = :schema
      AND table_type = 'BASE TABLE'
    ORDER BY table_name
    """,
    {"schema": schema},
)

if tables_df.empty:
    st.warning("Nessuna tabella trovata nello schema selezionato.")
    st.stop()

tables = tables_df["table_name"].tolist()

# Search box per filtrare la lista
filter_text = st.text_input("Filtra tabelle (contains)", value="")
if filter_text.strip():
    tables_filtered = [t for t in tables if filter_text.lower() in t.lower()]
else:
    tables_filtered = tables

if not tables_filtered:
    st.warning("Nessuna tabella corrisponde al filtro.")
    st.stop()

colA, colB = st.columns([2, 1])
with colA:
    selected_table = st.selectbox("Seleziona tabella", tables_filtered, index=0)
with colB:
    limit = st.number_input("Preview LIMIT", min_value=5, max_value=2000, value=20, step=5)

st.markdown("---")

# ------------------------------
# 4) Dettagli tabella
# ------------------------------
st.subheader("4) Dettagli tabella")

info_col1, info_col2 = st.columns(2)

with info_col1:
    try:
        count_df = query_df(f'SELECT COUNT(*) AS rows FROM "{schema}"."{selected_table}"')
        st.metric("Righe totali", f"{int(count_df.iloc[0, 0]):,}")
    except Exception as e:
        st.error("Errore nel COUNT(*)")
        st.exception(e)

with info_col2:
    try:
        cols_df = query_df(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
            ORDER BY ordinal_position
            """,
            {"schema": schema, "table": selected_table},
        )
        st.write("Colonne & tipi")
        st.dataframe(cols_df, use_container_width=True, height=240)
    except Exception as e:
        st.error("Errore nel recupero colonne")
        st.exception(e)

st.markdown("---")

# ------------------------------
# 5) Preview dati
# ------------------------------
st.subheader("5) Preview dati")

try:
    preview_df = query_df(f'SELECT * FROM "{schema}"."{selected_table}" LIMIT {int(limit)}')
    st.dataframe(preview_df, use_container_width=True)
except Exception as e:
    st.error("Errore nella preview")
    st.exception(e)

st.markdown("---")

# ------------------------------
# 6) Quick checks (DW sanity)
# ------------------------------
st.subheader("6) Quick checks (DW sanity)")

st.caption("Esegue alcuni controlli rapidi se le tabelle tipiche (game/review/date) sono presenti nello schema selezionato.")

# Controlla se esistono nel tuo schema
tables_lower = set(t.lower() for t in tables)
has_game = "game" in tables_lower
has_review = "review" in tables_lower
has_date = "date" in tables_lower

if not (has_game or has_review or has_date):
    st.warning(
        f"Nello schema `{schema}` non vedo le tabelle DW classiche (game/review/date). "
        "Se il vostro DW è in uno schema separato (es. `dwh`), selezionalo sopra."
    )

run_checks = st.checkbox("Esegui quick checks", value=False)

if run_checks:
    # Nota: se il nome tabella è Game in maiuscolo ma creato senza virgolette,
    # postgres lo salva in minuscolo; per questo usiamo nome minuscolo.
    checks = {}

    if has_game:
        checks["Game count"] = f'SELECT COUNT(*) AS n FROM "{schema}"."game"'
        checks["Game sample"] = f'SELECT * FROM "{schema}"."game" LIMIT 3'

    if has_review:
        checks["Review count"] = f'SELECT COUNT(*) AS n FROM "{schema}"."review"'
        checks["Review sample"] = f'SELECT * FROM "{schema}"."review" LIMIT 3'

    if has_date:
        checks["Date count"] = f'SELECT COUNT(*) AS n FROM "{schema}"."date"'
        checks["Date sample"] = f'SELECT * FROM "{schema}"."date" LIMIT 3'

    # Join checks solo se entrambe presenti
    if has_review and has_game:
        checks["Join Review -> Game"] = f'''
            SELECT COUNT(*) AS n
            FROM "{schema}"."review" r
            JOIN "{schema}"."game" g ON g."id_game" = r."id_game"
        '''

    if has_review and has_date:
        checks["Join Review -> Date"] = f'''
            SELECT COUNT(*) AS n
            FROM "{schema}"."review" r
            JOIN "{schema}"."date" d ON d."id_date" = r."id_date"
        '''

    for title, sql in checks.items():
        try:
            df = query_df(sql)
            # Se è un count, mostra numero; altrimenti dataframe
            if df.shape == (1, 1) and df.columns[0].lower() in ("n", "count", "rows"):
                st.write(f"**{title}** → {int(df.iloc[0, 0]):,}")
            else:
                st.write(f"**{title}**")
                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.warning(f"{title} → errore")
            st.code(sql)
            st.exception(e)

st.markdown("---")

# ------------------------------
# 7) Query custom (solo SELECT)
# ------------------------------
st.subheader("7) Query custom (solo SELECT)")

default_sql = f'SELECT * FROM "{schema}"."{selected_table}" LIMIT {int(limit)}'
user_sql = st.text_area("SQL", value=default_sql, height=160)

if st.button("Esegui query"):
    sql_stripped = user_sql.strip().lower()
    if not sql_stripped.startswith("select"):
        st.error("Per sicurezza, questa pagina accetta solo query che iniziano con SELECT.")
    else:
        try:
            df = query_df(user_sql)
            st.success(f"✅ Query OK — {len(df):,} righe")
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error("Errore nell'esecuzione della query")
            st.exception(e)

render_footer()