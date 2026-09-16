"""Modelos de leitura das respostas da API.

Todos sao `frozen`: e aqui que a premissa "o bot nao calcula nada" vira estrutura.
Nao existe setter e nao existe metodo de calculo -- `final_score` so pode ser
preenchido com o que o backend devolveu.

Campos conferidos contra a spec real do backend (`MyRank-backend`, filtro de bot).
`from_api` continua tolerante a campo ausente -- protege contra uma chave a mais ou
a menos, nao contra nome errado (isso o `KeyError`/teste pega, de proposito).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Json = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Category:
    id: int
    name: str
    is_default: bool = False

    @classmethod
    def from_api(cls, data: Json) -> Category:
        return cls(
            id=int(data["id"]),
            name=str(data.get("name", "")),
            is_default=bool(data.get("isDefault", data.get("default", False))),
        )


@dataclass(frozen=True, slots=True)
class Work:
    id: int
    title: str
    score: float
    final_score: float
    time_minutes: int
    category_id: int | None = None
    category_name: str | None = None
    image_url: str | None = None
    creator: str | None = None
    release_date: str | None = None
    # Posicao dentro da categoria, pronta do backend. So serve pra numerar o /ranking
    # quando filtrado por categoria -- em /works/unified (todas juntas) ela repete
    # entre categorias diferentes, entao la a numeracao e por ordem de lista mesmo.
    position: int | None = None

    @classmethod
    def from_api(cls, data: Json) -> Work:
        return cls(
            id=int(data["id"]),
            title=str(data.get("title", "")),
            score=float(data.get("score") or 0.0),
            final_score=float(data.get("finalScore") or 0.0),
            time_minutes=int(data.get("timeMinutes") or 0),
            category_id=_opt_int(data.get("categoryId")),
            category_name=_opt_str(data.get("categoryName")),
            image_url=_opt_str(data.get("imageUrl")),
            creator=_opt_str(data.get("creator")),
            release_date=_opt_str(data.get("releaseDate")),
            position=_opt_int(data.get("position")),
        )


@dataclass(frozen=True, slots=True)
class Badge:
    """`code` e o identificador real (nao ha `id` numerico na resposta)."""

    code: str
    name: str
    description: str
    unlocked: bool
    bucket: str | None = None
    has_progress: bool = False
    progress: int = 0
    target: int = 0
    icon: str | None = None
    unlocked_at: str | None = None

    @property
    def progress_ratio(self) -> float:
        """Fracao 0..1 para desenhar a barra. Nao e regra de negocio: o backend ja
        mandou `progress` e `target` prontos, isto so evita divisao por zero."""
        if self.target <= 0:
            return 1.0 if self.unlocked else 0.0
        return min(self.progress / self.target, 1.0)

    @classmethod
    def from_api(cls, data: Json) -> Badge:
        return cls(
            code=str(data.get("code", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            unlocked=bool(data.get("unlocked", False)),
            bucket=_opt_str(data.get("bucket")),
            has_progress=bool(data.get("hasProgress", False)),
            progress=int(data.get("progress") or 0),
            target=int(data.get("target") or 0),
            icon=_opt_str(data.get("icon")),
            unlocked_at=_opt_str(data.get("unlockedAt")),
        )


@dataclass(frozen=True, slots=True)
class ExternalResult:
    """Item da lista de `GET /external/search/{tipo}` -- o que vai no select."""

    external_id: str
    title: str
    year: str | None = None
    creator: str | None = None

    @classmethod
    def from_api(cls, data: Json) -> ExternalResult:
        return cls(
            external_id=str(data["externalId"]),
            title=str(data.get("title", "")),
            year=_opt_str(data.get("year") or _year_of(data.get("releaseDate"))),
            creator=_opt_str(data.get("creator")),
        )


@dataclass(frozen=True, slots=True)
class ExternalDetails:
    """Resposta de `GET /external/{tipo}/{id}`: ja vem com `timeMinutes` calculado
    pelo backend. O bot nao estima duracao."""

    external_id: str
    title: str
    time_minutes: int
    image_url: str | None = None
    creator: str | None = None
    release_date: str | None = None

    @classmethod
    def from_api(cls, data: Json) -> ExternalDetails:
        return cls(
            external_id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            time_minutes=int(data.get("timeMinutes") or 0),
            image_url=_opt_str(data.get("imageUrl")),
            creator=_opt_str(data.get("creator")),
            release_date=_opt_str(data.get("releaseDate")),
        )


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _year_of(release_date: Any) -> str | None:
    text = _opt_str(release_date)
    return text[:4] if text and len(text) >= 4 else None
