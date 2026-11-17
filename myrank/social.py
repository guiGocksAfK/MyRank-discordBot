"""Modelos de leitura da area social (`/api/social`).

Mesma regra de `models.py`: frozen, sem calculo. Quem decide o que a pessoa pode ver
(perfil trancado, take de perfil privado) e o backend; aqui so se le o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from myrank.models import Json, _opt_int, _opt_str

REACTIONS: tuple[tuple[str, str], ...] = (
    ("up", "\U0001f44d"), ("agree", "Concordo"), ("disagree", "Discordo"),
)


@dataclass(frozen=True, slots=True)
class Actor:
    id: int
    username: str
    avatar_url: str | None = None

    @classmethod
    def from_api(cls, data: Any) -> Actor:
        data = data if isinstance(data, dict) else {}
        return cls(int(data.get("id") or 0), str(data.get("username") or "?"),
                   _opt_str(data.get("avatarUrl")))


@dataclass(frozen=True, slots=True)
class WorkMini:
    id: int
    title: str
    type: str | None = None
    image_url: str | None = None
    score: float | None = None

    @classmethod
    def from_api(cls, data: Json) -> WorkMini:
        score = data.get("score")
        return cls(int(data.get("id") or 0), str(data.get("title") or ""),
                   _opt_str(data.get("type")), _opt_str(data.get("imageUrl")),
                   None if score is None else float(score))


@dataclass(frozen=True, slots=True)
class BadgeMini:
    code: str
    name: str
    icon: str | None = None

    @classmethod
    def from_api(cls, data: Json) -> BadgeMini:
        return cls(str(data.get("code") or ""), str(data.get("name") or ""),
                   _opt_str(data.get("icon")))


@dataclass(frozen=True, slots=True)
class Reactions:
    up: int = 0
    agree: int = 0
    disagree: int = 0
    mine: str | None = None  # "up" | "agree" | "disagree" | None

    def count(self, kind: str) -> int:
        return int(getattr(self, kind, 0))

    @classmethod
    def from_api(cls, data: Any) -> Reactions:
        data = data if isinstance(data, dict) else {}
        return cls(int(data.get("up") or 0), int(data.get("agree") or 0),
                   int(data.get("disagree") or 0), _opt_str(data.get("mine")))


@dataclass(frozen=True, slots=True)
class FeedItem:
    """`type` TAKE: work, take_text, score, reacoes e comentarios. `type` RATED_DAY:
    works (ate 8) e work_count, as obras que a pessoa avaliou num dia (id negativo:
    nao recebe reacao)."""

    id: int
    type: str
    actor: Actor
    created_at: str | None = None
    work: WorkMini | None = None
    take_text: str | None = None
    take_id: int | None = None
    comment_count: int = 0
    take_edited: bool = False
    can_manage: bool = False
    score: float | None = None
    reactions: Reactions = field(default_factory=Reactions)
    works: tuple[WorkMini, ...] = ()
    work_count: int = 0

    @property
    def is_take(self) -> bool:
        return self.type == "TAKE" and self.take_id is not None

    @classmethod
    def from_api(cls, data: Json) -> FeedItem:
        work = data.get("work")
        score = data.get("score")
        return cls(
            id=int(data["id"]),
            type=str(data.get("type") or ""),
            actor=Actor.from_api(data.get("actor")),
            created_at=_opt_str(data.get("createdAt")),
            work=WorkMini.from_api(work) if isinstance(work, dict) else None,
            take_text=_opt_str(data.get("takeText")),
            take_id=_opt_int(data.get("takeId")),
            comment_count=int(data.get("commentCount") or 0),
            take_edited=bool(data.get("takeEdited")),
            can_manage=bool(data.get("canManage")),
            score=None if score is None else float(score),
            reactions=Reactions.from_api(data.get("reactions")),
            works=tuple(WorkMini.from_api(w) for w in data.get("works") or ()),
            work_count=int(data.get("workCount") or 0),
        )


@dataclass(frozen=True, slots=True)
class SocialUser:
    """Card de pessoa nas listas (seguindo, seguidores, sugestoes, busca, pedidos)."""

    id: int
    username: str
    avatar_url: str | None = None
    bio: str | None = None
    works_count: int = 0
    avg_score: float = 0.0
    following: bool = False
    follows_you: bool = False
    is_public: bool = False
    requested: bool = False
    shared_count: int = 0
    match_pct: int | None = None
    fight_title: str | None = None
    fight_mine: float | None = None
    fight_theirs: float | None = None

    @classmethod
    def from_api(cls, data: Json) -> SocialUser:
        return cls(
            id=int(data["id"]),
            username=str(data.get("username") or "?"),
            avatar_url=_opt_str(data.get("avatarUrl")),
            bio=_opt_str(data.get("bio")),
            works_count=int(data.get("worksCount") or 0),
            avg_score=float(data.get("avgScore") or 0.0),
            following=bool(data.get("following")),
            follows_you=bool(data.get("followsYou")),
            is_public=bool(data.get("isPublic", data.get("public", False))),
            requested=bool(data.get("requested")),
            shared_count=int(data.get("sharedCount") or 0),
            match_pct=_opt_int(data.get("matchPct")),
            fight_title=_opt_str(data.get("fightTitle")),
            fight_mine=_opt_float(data.get("fightMine")),
            fight_theirs=_opt_float(data.get("fightTheirs")),
        )


@dataclass(frozen=True, slots=True)
class SocialProfile:
    """`locked`: perfil privado de quem a pessoa nao segue -- so cabecalho e
    contagens; as listas vem vazias do backend."""

    id: int
    username: str
    avatar_url: str | None = None
    bio: str | None = None
    works_count: int = 0
    avg_score: float = 0.0
    following: bool = False
    follows_you: bool = False
    is_public: bool = False
    requested: bool = False
    locked: bool = False
    follower_count: int = 0
    following_count: int = 0
    top: tuple[WorkMini, ...] = ()
    breakdown: tuple[tuple[str, int], ...] = ()
    badges: tuple[BadgeMini, ...] = ()
    works: tuple[WorkMini, ...] = ()

    @classmethod
    def from_api(cls, data: Json) -> SocialProfile:
        breakdown = data.get("breakdown")
        return cls(
            id=int(data["id"]),
            username=str(data.get("username") or "?"),
            avatar_url=_opt_str(data.get("avatarUrl")),
            bio=_opt_str(data.get("bio")),
            works_count=int(data.get("worksCount") or 0),
            avg_score=float(data.get("avgScore") or 0.0),
            following=bool(data.get("following")),
            follows_you=bool(data.get("followsYou")),
            is_public=bool(data.get("isPublic", data.get("public", False))),
            requested=bool(data.get("requested")),
            locked=bool(data.get("locked")),
            follower_count=int(data.get("followerCount") or 0),
            following_count=int(data.get("followingCount") or 0),
            top=tuple(WorkMini.from_api(w) for w in data.get("top") or ()),
            breakdown=tuple(
                (str(k), int(v)) for k, v in breakdown.items()
            ) if isinstance(breakdown, dict) else (),
            badges=tuple(BadgeMini.from_api(b) for b in data.get("badges") or ()),
            works=tuple(WorkMini.from_api(w) for w in data.get("works") or ()),
        )


@dataclass(frozen=True, slots=True)
class SocialSummary:
    following: int = 0
    followers: int = 0
    feed_count: int = 0
    pending_follow_requests: int = 0

    @classmethod
    def from_api(cls, data: Any) -> SocialSummary:
        data = data if isinstance(data, dict) else {}
        return cls(int(data.get("following") or 0), int(data.get("followers") or 0),
                   int(data.get("feedCount") or 0), int(data.get("pendingFollowRequests") or 0))


@dataclass(frozen=True, slots=True)
class TakeComment:
    """Comentario de take. So os da raiz tem `replies` (um nivel, como no site)."""

    id: int
    take_id: int
    author: Actor
    text: str
    parent_id: int | None = None
    created_at: str | None = None
    edited: bool = False
    can_edit: bool = False
    can_delete: bool = False
    replies: tuple[TakeComment, ...] = ()

    @classmethod
    def from_api(cls, data: Json) -> TakeComment:
        return cls(
            id=int(data["id"]),
            take_id=int(data.get("takeId") or 0),
            author=Actor.from_api(data.get("author")),
            text=str(data.get("text") or ""),
            parent_id=_opt_int(data.get("parentId")),
            created_at=_opt_str(data.get("createdAt")),
            edited=bool(data.get("edited")),
            can_edit=bool(data.get("canEdit")),
            can_delete=bool(data.get("canDelete")),
            replies=tuple(TakeComment.from_api(r) for r in data.get("replies") or ()),
        )


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)
