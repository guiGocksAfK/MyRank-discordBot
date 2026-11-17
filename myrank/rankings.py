"""Ranking de criadores (`/api/rankings/creators`). A conta inteira -- separar nomes,
juntar duplas, media, bonus de volume -- e do backend; aqui so se le."""

from __future__ import annotations

from dataclasses import dataclass

from myrank.models import Json
from myrank.social import WorkMini

UNIFIED_SORTS: tuple[tuple[str, str], ...] = (
    ("score", "Nota"), ("weighted", "Nota ponderada"), ("time", "Tempo"),
)
CREATOR_ORDERS: tuple[tuple[str, str], ...] = (
    ("avg", "Media"), ("weighted", "Ponderada"), ("works", "Mais obras"),
)
CREATOR_TYPES: tuple[str, ...] = ("Diretor", "Escritor", "Studio", "Criador")


@dataclass(frozen=True, slots=True)
class CreatorRank:
    """`average` e a media pura; `score` e o que ordena (igual a media, ou a ponderada)."""

    id: str
    name: str
    type: str
    count: int
    average: float
    score: float
    works: tuple[WorkMini, ...] = ()

    @classmethod
    def from_api(cls, data: Json) -> CreatorRank:
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or "?"),
            type=str(data.get("type") or "Criador"),
            count=int(data.get("count") or 0),
            average=float(data.get("average") or 0.0),
            score=float(data.get("score") or 0.0),
            works=tuple(WorkMini.from_api(w) for w in data.get("works") or ()),
        )
