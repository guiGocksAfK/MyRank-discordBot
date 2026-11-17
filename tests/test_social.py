"""Area social: modelos, rotas do client e telas."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx
import pytest

from myrank.social import FeedItem, Reactions, SocialProfile, SocialUser, TakeComment
from tests.conftest import ClientFactory
from ui import social_embeds as se
from ui.social import (
    CommentsView,
    FeedView,
    PeopleView,
    ProfileView,
    ReactionButton,
    TakeView,
    TextModal,
)
from ui.views import ConfirmView

TAKE_JSON = {
    "id": 40, "type": "TAKE", "actor": {"id": 2, "username": "ana", "avatarUrl": None},
    "createdAt": "2026-11-10T20:00:00", "work": {"id": 7, "title": "Duna", "type": "filme",
                                                 "imageUrl": "https://img/d.jpg", "score": 9.5},
    "takeText": "Melhor ficcao do ano", "takeId": 11, "commentCount": 2, "takeEdited": False,
    "canManage": True, "score": 9.5,
    "reactions": {"up": 3, "agree": 1, "disagree": 0, "mine": "up"},
    "works": [], "workCount": 0,
}
DAY_JSON = {
    "id": -5, "type": "RATED_DAY", "actor": {"id": 3, "username": "bia"},
    "createdAt": "2026-11-09T10:00:00", "works": [
        {"id": i, "title": f"Obra {i}", "type": "jogo"} for i in range(8)
    ], "workCount": 11, "reactions": None,
}
TAKE = FeedItem.from_api(TAKE_JSON)
DAY = FeedItem.from_api(DAY_JSON)
PUBLICO = SocialProfile(5, "caio", is_public=True, works_count=2, avg_score=7.5,
                        works=(), follower_count=1)
PRIVADO = SocialProfile(6, "dani", locked=True)


def interaction() -> Any:
    value = MagicMock()
    value.user.id = 123
    value.response.defer = AsyncMock()
    value.response.edit_message = AsyncMock()
    value.response.send_modal = AsyncMock()
    value.response.send_message = AsyncMock()
    value.edit_original_response = AsyncMock()
    value.followup.send = AsyncMock()
    return value


def labels(view: discord.ui.View) -> list[str]:
    """Na ordem em que aparecem na tela: por linha, depois na ordem de entrada."""
    buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
    return [c.label or "" for c in sorted(buttons, key=lambda c: c.row or 0)]


# ------------------------------------------------------------------ modelos e embeds

def test_feed_items_parse() -> None:
    assert TAKE.is_take and TAKE.reactions == Reactions(3, 1, 0, "up")
    assert TAKE.work is not None and TAKE.work.score == 9.5
    assert not DAY.is_take and DAY.work_count == 11 and len(DAY.works) == 8


def test_feed_embed_shows_takes_and_rated_days() -> None:
    embed = se.feed([TAKE, DAY], 0, following_only=False)
    names = [f.name or "" for f in embed.fields]
    assert names[0] == "ana sobre Duna (9.5) · 10/11/2026"
    assert names[1].startswith("bia avaliou 11 obra(s)")
    assert "e mais 7" in (embed.fields[1].value or "")
    assert "(voce)" in (embed.fields[0].value or "")  # a reacao da pessoa aparece
    assert se.feed([], 0, False).description == se.FEED_EMPTY
    assert se.feed([], 3, False).description == "Fim do feed."


@pytest.mark.parametrize(("profile", "label"), [
    (SocialProfile(1, "a", is_public=True), "Seguir"),
    (SocialProfile(1, "a", is_public=False), "Pedir para seguir"),
    (SocialProfile(1, "a", requested=True), "Cancelar pedido"),
    (SocialProfile(1, "a", following=True, is_public=True), "Deixar de seguir"),
])
def test_follow_button_says_what_the_click_does(profile: SocialProfile, label: str) -> None:
    assert se.follow_label(profile) == label
    assert labels(ProfileView(MagicMock(), 123, profile))[0] == label


def test_locked_profile_hides_content() -> None:
    embed = se.social_profile(PRIVADO)
    assert any("privado" in (f.name or "") for f in embed.fields)
    assert "Ver obras" not in labels(ProfileView(MagicMock(), 123, PRIVADO))


def test_avatar_only_when_https() -> None:
    assert se.social_profile(SocialProfile(1, "a", avatar_url="https://x/a.png")).thumbnail.url
    assert not se.social_profile(SocialProfile(1, "a", avatar_url="data:abc")).thumbnail.url


# ------------------------------------------------------------------ perfil

async def test_follow_toggles_and_redraws_from_backend() -> None:
    api: Any = MagicMock()
    api.toggle_follow = AsyncMock()
    seguindo = SocialProfile(5, "caio", is_public=True, following=True)
    api.profile = AsyncMock(return_value=seguindo)
    view = ProfileView(api, 123, PUBLICO)
    i = interaction()
    await view.follow.callback(i)
    api.toggle_follow.assert_awaited_once_with(123, 5)
    new_view = i.edit_original_response.call_args.kwargs["view"]
    assert labels(new_view)[0] == "Deixar de seguir"


# ------------------------------------------------------------------ pessoas

def users(n: int) -> list[SocialUser]:
    return [SocialUser(i, f"p{i}", is_public=True) for i in range(n)]


async def test_people_menu_follows_the_page() -> None:
    view = PeopleView(MagicMock(), 123, "Seguindo", users(10), empty="-")
    select = next(c for c in view.children if isinstance(c, discord.ui.Select))
    assert [o.label for o in select.options] == [f"p{i}" for i in range(8)]
    await view.next_page.callback(interaction())
    select = next(c for c in view.children if isinstance(c, discord.ui.Select))
    assert [o.label for o in select.options] == ["p8", "p9"]


def test_empty_people_list_has_no_buttons() -> None:
    view = PeopleView(MagicMock(), 123, "Seguindo", [], empty="Ninguem.")
    assert view.children == []
    assert view.embed().description == "Ninguem."


async def test_follow_request_approved_leaves_the_list() -> None:
    api: Any = MagicMock()
    api.answer_follow_request = AsyncMock()
    view = PeopleView(api, 123, "Pedidos", users(2), empty="Nenhum.", requests=True)
    view.message = MagicMock()
    view.message.edit = AsyncMock()
    i = interaction()
    await view._on_pick(i, "1")
    answer = i.response.send_message.call_args.kwargs["view"]
    assert labels(answer) == ["Aprovar", "Recusar"]
    await answer.approve.callback(interaction())
    api.answer_follow_request.assert_awaited_once_with(123, 1, approve=True)
    assert [u.id for u in view._users] == [0]


# ------------------------------------------------------------------ feed

async def test_feed_pages_come_from_the_backend() -> None:
    api: Any = MagicMock()
    api.feed = AsyncMock(return_value=[])
    view = FeedView(api, 123, [TAKE, DAY], following_only=True)
    assert view.previous_page.disabled and not view.next_page.disabled
    select = next(c for c in view.children if isinstance(c, discord.ui.Select))
    assert [o.value for o in select.options] == ["40"]  # so takes abrem
    i = interaction()
    await view.next_page.callback(i)
    api.feed.assert_awaited_once_with(123, 1, 8, following_only=True)
    last = i.edit_original_response.call_args.kwargs["view"]
    assert last.next_page.disabled  # pagina vazia = fim


# ------------------------------------------------------------------ take

def test_take_buttons() -> None:
    view = TakeView(MagicMock(), 123, TAKE)
    assert labels(view) == ["\U0001f44d 3", "Concordo 1", "Discordo 0", "Comentarios (2)",
                            "Editar", "Apagar"]
    other = TakeView(MagicMock(), 123, FeedItem.from_api({**TAKE_JSON, "canManage": False}))
    assert "Editar" not in labels(other)


async def test_react_redraws_with_backend_counts() -> None:
    api: Any = MagicMock()
    api.react = AsyncMock(return_value=Reactions(2, 1, 0, None))
    view = TakeView(api, 123, TAKE)
    i = interaction()
    up = next(c for c in view.children if isinstance(c, ReactionButton) and c.kind == "up")
    await up.callback(i)
    api.react.assert_awaited_once_with(123, 40, "up")  # id do evento, nao do take
    assert labels(i.edit_original_response.call_args.kwargs["view"])[0] == "\U0001f44d 2"


async def test_edit_take() -> None:
    api: Any = MagicMock()
    api.edit_take = AsyncMock(return_value=TAKE)
    view = TakeView(api, 123, TAKE)
    i = interaction()
    await view.edit.callback(i)
    modal = i.response.send_modal.call_args.args[0]
    assert isinstance(modal, TextModal) and modal.text.default == "Melhor ficcao do ano"
    modal.text._value = "Mudei de ideia"
    await modal.on_submit(interaction())
    api.edit_take.assert_awaited_once_with(123, 11, "Mudei de ideia")


async def test_delete_take_asks_first() -> None:
    api: Any = MagicMock()
    api.delete_take = AsyncMock()
    view = TakeView(api, 123, TAKE)
    i = interaction()
    await view.delete.callback(i)
    confirm = i.response.edit_message.call_args.kwargs["view"]
    assert isinstance(confirm, ConfirmView)
    api.delete_take.assert_not_called()
    await confirm._on_confirm(interaction())
    api.delete_take.assert_awaited_once_with(123, 11)


# ------------------------------------------------------------------ comentarios

ROOTS = [TakeComment.from_api({
    "id": 1, "takeId": 11, "author": {"id": 9, "username": "eu"}, "text": "Concordo",
    "canEdit": True, "canDelete": True,
    "replies": [{"id": 2, "takeId": 11, "parentId": 1, "author": {"id": 2, "username": "ana"},
                 "text": "Valeu", "canEdit": False, "canDelete": True}],
})]


def test_comments_buttons_and_embed() -> None:
    view = CommentsView(MagicMock(), 123, TAKE, ROOTS)
    assert labels(view) == ["Comentar", "Responder", "Editar meu", "Apagar"]
    assert labels(CommentsView(MagicMock(), 123, TAKE, [])) == ["Comentar"]
    text = se.comments(TAKE, ROOTS).description or ""
    assert "**eu**: Concordo" in text and "↳ **ana**: Valeu" in text


async def test_reply_goes_to_the_chosen_comment_and_reloads() -> None:
    api: Any = MagicMock()
    api.add_comment = AsyncMock()
    api.comments = AsyncMock(return_value=ROOTS)
    view = CommentsView(api, 123, TAKE, ROOTS)
    i = interaction()
    await view.reply.callback(i)
    pick = i.response.edit_message.call_args.kwargs["view"].children[0]
    j = interaction()
    await pick._on_pick(j, "1")
    modal = j.response.send_modal.call_args.args[0]
    modal.text._value = "Boa"
    k = interaction()
    await modal.on_submit(k)
    api.add_comment.assert_awaited_once_with(123, 11, "Boa", 1)
    assert isinstance(k.edit_original_response.call_args.kwargs["view"], CommentsView)


async def test_comment_error_keeps_the_screen() -> None:
    api: Any = MagicMock()
    api.add_comment = AsyncMock(side_effect=RuntimeError("x"))
    view = CommentsView(api, 123, TAKE, ROOTS)
    i = interaction()
    await view.add.callback(i)
    modal = i.response.send_modal.call_args.args[0]
    modal.text._value = "Oi"
    j = interaction()
    await modal.on_submit(j)
    j.followup.send.assert_awaited_once()
    j.edit_original_response.assert_not_called()


# ------------------------------------------------------------------ client

async def test_client_social_routes(make_client: ClientFactory) -> None:
    seen: list[tuple[str, str, str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, str(request.url.params), body))
        path = request.url.path
        if request.method == "DELETE" or path.endswith(("/approve", "/reject")):
            return httpx.Response(204)
        if path.endswith("/react"):
            return httpx.Response(200, json={"up": 1, "agree": 0, "disagree": 0, "mine": "up"})
        if "/takes" in path and request.method != "GET":
            if path.endswith("/comments"):
                return httpx.Response(200, json={"id": 1, "takeId": 11, "text": "x"})
            return httpx.Response(200, json=TAKE_JSON)
        if path.startswith("/api/social/users/"):
            return httpx.Response(200, json={"id": 5, "username": "caio", "isPublic": True})
        if path.startswith("/api/social/follow/"):
            return httpx.Response(200, json={"id": 5, "username": "caio", "following": True})
        if path.endswith("/summary"):
            return httpx.Response(200, json={"following": 2, "followers": 3})
        return httpx.Response(200, json=[])

    client = await make_client(handler)
    assert (await client.social_summary(1)).followers == 3
    await client.feed(1, 2, 8, following_only=True)
    await client.people(1, "followers")
    await client.search_users(1, "ca")
    assert (await client.profile(1, 5)).is_public
    assert (await client.toggle_follow(1, 5)).following
    await client.answer_follow_request(1, 9, approve=False)
    assert (await client.react(1, 40, "up")).mine == "up"
    await client.post_take(1, 7, "Muito bom")
    await client.edit_take(1, 11, "Muito bom!")
    await client.delete_take(1, 11)
    await client.add_comment(1, 11, "oi", 3)
    with pytest.raises(ValueError):
        await client.people(1, "admins")
    assert seen == [
        ("GET", "/api/social/summary", "", None),
        ("GET", "/api/social/feed", "page=2&size=8&scope=following", None),
        ("GET", "/api/social/followers", "", None),
        ("GET", "/api/social/users", "q=ca", None),
        ("GET", "/api/social/users/5", "", None),
        ("POST", "/api/social/follow/5", "", None),
        ("POST", "/api/social/follow-requests/9/reject", "", None),
        ("POST", "/api/social/feed/40/react", "", {"kind": "up"}),
        ("POST", "/api/social/takes", "", {"workId": 7, "text": "Muito bom"}),
        ("PATCH", "/api/social/takes/11", "", {"text": "Muito bom!"}),
        ("DELETE", "/api/social/takes/11", "", None),
        ("POST", "/api/social/takes/11/comments", "", {"text": "oi", "parentCommentId": 3}),
    ]
