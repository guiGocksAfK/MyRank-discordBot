"""A propria conta (`GET`/`PUT /api/users/me`): o que a tela de Configuracoes do site
mostra e muda. O backend libera so esses dois para o bot -- excluir a conta e sair
dos aparelhos continuam so no site."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from myrank.models import Json, _opt_str

LANGUAGES: tuple[tuple[str, str], ...] = (("PT", "Português"), ("EN", "English"), ("ES", "Español"))
DM_POLICIES: tuple[tuple[str, str], ...] = (
    ("EVERYONE", "Qualquer pessoa"), ("FOLLOWING", "Só quem eu sigo"),
)
NOTIFICATION_GROUPS: tuple[tuple[str, str], ...] = (
    ("FOLLOWS", "Seguidores e pedidos"), ("REACTIONS", "Reações"),
    ("COMMENTS", "Comentários"), ("TAKES", "Takes de quem eu sigo"), ("GROUPS", "Grupos do chat"),
)
RANKINGS_VIEWS: tuple[tuple[str, str], ...] = (("LIST", "Lista"), ("GRID", "Grade"))


@dataclass(frozen=True, slots=True)
class Account:
    id: int
    username: str
    bio: str | None = None
    avatar_url: str | None = None
    is_public: bool = False
    language: str = "PT"
    dm_policy: str = "EVERYONE"
    muted_notifications: tuple[str, ...] = ()
    weighted_by_default: bool = False
    rankings_view: str = "LIST"
    auth_provider: str = "LOCAL"

    @classmethod
    def from_api(cls, data: Json) -> Account:
        return cls(
            id=int(data["id"]),
            username=str(data.get("username") or ""),
            bio=_opt_str(data.get("bio")),
            avatar_url=_opt_str(data.get("avatarUrl")),
            is_public=bool(data.get("isPublic", data.get("public", False))),
            language=str(data.get("language") or "PT").upper(),
            dm_policy=str(data.get("dmPolicy") or "EVERYONE").upper(),
            muted_notifications=tuple(str(g).upper() for g in data.get("mutedNotifications") or ()),
            weighted_by_default=bool(data.get("weightedByDefault")),
            rankings_view=str(data.get("rankingsView") or "LIST").upper(),
            auth_provider=str(data.get("authProvider") or "LOCAL").upper(),
        )


def profile_changes(
    account: Account, *, username: str, bio: str, avatar_url: str
) -> dict[str, Any]:
    """So o que mudou no modal de perfil (o PUT e parcial). Bio e foto vazias apagam."""
    changes: dict[str, Any] = {}
    if username != account.username:
        changes["username"] = username
    if bio != (account.bio or ""):
        changes["bio"] = bio
    if avatar_url != (account.avatar_url or ""):
        changes["avatarUrl"] = avatar_url
    return changes


def label_of(options: tuple[tuple[str, str], ...], value: str) -> str:
    return dict(options).get(value, value)
