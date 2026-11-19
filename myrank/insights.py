"""Modelos de leitura das notificacoes (`/api/notifications`) e da IA Insights
(`/api/insights`).

A IA escreve os textos e o backend calcula os numeros (perfil de gosto, orcamento
diario de mensagens); o bot so exibe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from myrank.models import Json, _opt_int, _opt_str
from myrank.social import Actor, WorkMini


@dataclass(frozen=True, slots=True)
class Notification:
    """`title` e `message` ja vem prontos do backend, em portugues."""

    id: int
    type: str
    read: bool
    title: str
    message: str
    created_at: str | None = None
    actor: Actor | None = None
    actor_count: int = 0
    work: WorkMini | None = None

    @classmethod
    def from_api(cls, data: Json) -> Notification:
        actor = data.get("actor")
        work = data.get("work")
        return cls(
            id=int(data["id"]),
            type=str(data.get("type") or ""),
            read=bool(data.get("read")),
            title=str(data.get("title") or ""),
            message=str(data.get("message") or ""),
            created_at=_opt_str(data.get("updatedAt") or data.get("createdAt")),
            actor=Actor.from_api(actor) if isinstance(actor, dict) else None,
            actor_count=int(data.get("actorCount") or 0),
            work=WorkMini.from_api(work) if isinstance(work, dict) else None,
        )


@dataclass(frozen=True, slots=True)
class Trait:
    icon: str
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class TasteSlice:
    """`average` e `count` sao calculados pelo backend; `percent` so existe nas
    analises antigas."""

    name: str
    average: float | None = None
    count: int | None = None
    percent: int | None = None


@dataclass(frozen=True, slots=True)
class Recommendation:
    title: str
    reason: str
    year: int | None = None
    category: str | None = None
    poster_url: str | None = None


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str  # "USER" | "AI"
    content: str

    @property
    def is_user(self) -> bool:
        return self.role == "USER"


@dataclass(frozen=True, slots=True)
class Insight:
    id: int
    title: str
    summary: str
    traits: tuple[Trait, ...] = ()
    contradictions: tuple[tuple[str, str], ...] = ()  # (icone, texto)
    taste: tuple[TasteSlice, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    work_count: int = 0
    cached: bool = False
    generated_at: str | None = None
    chat: tuple[ChatMessage, ...] = ()
    daily_remaining: int = 0
    daily_limit: int = 0

    @classmethod
    def from_api(cls, data: Json) -> Insight:
        analysis = data.get("analysis")
        analysis = analysis if isinstance(analysis, dict) else {}
        return cls(
            id=int(data["id"]),
            title=str(analysis.get("summaryTitle") or "Sua analise"),
            summary=str(analysis.get("summaryText") or ""),
            traits=tuple(
                Trait(str(t.get("icon") or ""), str(t.get("label") or ""),
                      str(t.get("description") or ""))
                for t in _dicts(analysis.get("traits"))
            ),
            contradictions=tuple(
                (str(c.get("icon") or ""), str(c.get("text") or ""))
                for c in _dicts(analysis.get("contradictions"))
            ),
            taste=tuple(
                TasteSlice(str(s.get("name") or ""), _opt_float(s.get("average")),
                           _opt_int(s.get("count")), _opt_int(s.get("percent")))
                for s in _dicts(analysis.get("tasteProfile"))
            ),
            recommendations=tuple(
                Recommendation(str(r.get("title") or ""), str(r.get("reason") or ""),
                               _opt_int(r.get("year")), _opt_str(r.get("category")),
                               _opt_str(r.get("posterUrl")))
                for r in _dicts(analysis.get("recommendations"))
                if r.get("title")
            ),
            work_count=int(data.get("workCount") or 0),
            cached=bool(data.get("cached")),
            generated_at=_opt_str(data.get("generatedAt")),
            chat=tuple(
                ChatMessage(str(m.get("role") or ""), str(m.get("content") or ""))
                for m in _dicts(data.get("chat"))
            ),
            daily_remaining=int(data.get("dailyRemaining") or 0),
            daily_limit=int(data.get("dailyLimit") or 0),
        )


def _dicts(value: Any) -> list[Json]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)
