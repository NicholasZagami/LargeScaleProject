# frontend/utils/data_access.py
from __future__ import annotations
from dataclasses import dataclass


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


def get_kpis() -> KPIs:
    """Valori mockati per ora."""
    return KPIs(
        total_games=125_000,
        total_reviews=10_500_000,
        avg_rating=4.1,
    )


def get_datasets_info() -> list[DatasetInfo]:
    """Riassunto dei due dataset principali (mock)."""
    return [
        DatasetInfo(
            name="Games dataset",
            description=(
                "Informazioni sui giochi: prezzo, publisher, genere, "
                "data di rilascio, valutazioni globali, ecc."
            ),
            rows_approx=125_000,
            columns_approx=40,
        ),
        DatasetInfo(
            name="Reviews dataset",
            description=(
                "Recensioni utente sui giochi Steam: rating, testo, data, "
                "ore di gioco e, in futuro, il sentiment estratto."
            ),
            rows_approx=10_500_000,
            columns_approx=25,
        ),
    ]