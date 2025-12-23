"""
db.py
-----

Questo modulo è il *livello infrastrutturale* di accesso ai dati.

Responsabilità:
- leggere la stringa di connessione dal file .env
- creare e mantenere una connessione a Postgres (SQLAlchemy Engine)
- fornire una funzione generica per eseguire query SQL e ottenere DataFrame

NON deve contenere:
- logica di business
- KPI
- query specifiche per dashboard

In altre parole:
db.py = "come parlo con il database"
"""
from __future__ import annotations

import os
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

# Carica variabili d'ambiente dal file .env (se presente)
load_dotenv()

_ENGINE: Engine | None = None


def get_engine() -> Engine:
    """
    Restituisce (o crea la prima volta) l'engine SQLAlchemy per Postgres.
    Usa la variabile d'ambiente POSTGRES_CONNECTION_STRING.
    """
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE

    conn_str = os.getenv("POSTGRES_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError(
            "POSTGRES_CONNECTION_STRING non trovata nel file .env.\n"
            "Esempio:\n"
            "postgresql+psycopg2://user:password@localhost:5432/dwh"
        )

    _ENGINE = create_engine(conn_str, pool_pre_ping=True)
    return _ENGINE


def query_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    """
    Esegue una query SQL (SELECT) e restituisce il risultato come pandas DataFrame.
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)