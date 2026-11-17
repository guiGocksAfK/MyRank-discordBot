"""/config e o /perfil proprio."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx

from cogs.profile import ProfileCog
from myrank.account import Account, profile_changes
from myrank.errors import ApiUnavailableError
from myrank.social import SocialProfile, SocialSummary
from tests.conftest import ClientFactory
from ui.config import ConfigView, ProfileModal, config_embed

CONTA = Account(1, "gui", bio="oi", avatar_url=None, is_public=False, language="PT",
                dm_policy="EVERYONE", muted_notifications=("REACTIONS",),
                weighted_by_default=False, rankings_view="LIST", auth_provider="DISCORD")


def interaction() -> Any:
    value = MagicMock()
    value.user.id = 123
    value.user.display_name = "Gui"
    value.user.display_avatar.url = "https://cdn/discord.png"
    value.response.defer = AsyncMock()
    value.response.send_modal = AsyncMock()
    value.response.send_message = AsyncMock()
    value.edit_original_response = AsyncMock()
    value.followup.send = AsyncMock()
    return value


def selects(view: discord.ui.View) -> list[discord.ui.Select[Any]]:
    return [c for c in view.children if isinstance(c, discord.ui.Select)]


def test_embed_shows_every_setting() -> None:
    embed = config_embed(CONTA)
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Perfil"] == "Privado"
    assert fields["Idioma"] == "Português"
    assert fields["Avisos silenciados"] == "Reações"
    assert fields["Como voce entra"] == "Discord"
    assert "excluir a conta: so no site" in (embed.footer.text or "")


def test_view_reflects_current_values() -> None:
    view = ConfigView(MagicMock(), 123, CONTA)
    assert view.weighted.label == "Nota ponderada: desligada"
    assert view.view_mode.label == "Rankings em: Lista"
    privacy, language, _dm, muted = selects(view)
    assert [o.value for o in privacy.options if o.default] == ["private"]
    assert [o.value for o in language.options if o.default] == ["PT"]
    assert [o.value for o in muted.options if o.default] == ["REACTIONS"]
    assert muted.min_values == 0  # nenhum silenciado = recebe tudo


async def test_each_control_saves_only_its_field() -> None:
    api: Any = MagicMock()
    api.update_me = AsyncMock(return_value=CONTA)
    view = ConfigView(api, 123, CONTA)
    await view.weighted.callback(interaction())
    await view.view_mode.callback(interaction())
    privacy, language, dm, muted = selects(view)
    picks: list[tuple[discord.ui.Select[Any], list[Any]]] = [
        (privacy, ["public"]), (language, ["ES"]), (dm, ["FOLLOWING"]), (muted, []),
    ]
    for select, values in picks:
        select._values = values
        await select.callback(interaction())
    sent = [call.args[1] for call in api.update_me.call_args_list]
    assert sent == [
        {"weightedByDefault": True}, {"rankingsView": "GRID"}, {"isPublic": True},
        {"language": "ES"}, {"dmPolicy": "FOLLOWING"}, {"mutedNotifications": []},
    ]


def test_profile_changes_only_what_changed() -> None:
    assert profile_changes(CONTA, username="gui", bio="oi", avatar_url="") == {}
    assert profile_changes(CONTA, username="guigo", bio="", avatar_url="https://a/b.png") == {
        "username": "guigo", "bio": "", "avatarUrl": "https://a/b.png",
    }


async def test_profile_modal_rejects_non_https_photo() -> None:
    api: Any = MagicMock()
    modal = ProfileModal(ConfigView(api, 123, CONTA))
    modal.username._value = "gui"
    modal.bio._value = "oi"
    modal.avatar._value = "http://inseguro/a.png"
    i = interaction()
    await modal.on_submit(i)
    api.update_me.assert_not_called()
    i.response.send_message.assert_awaited_once()


async def test_profile_modal_rejects_short_trimmed_username() -> None:
    api: Any = MagicMock()
    modal = ProfileModal(ConfigView(api, 123, CONTA))
    modal.username._value = "  a "
    modal.bio._value = ""
    modal.avatar._value = ""
    i = interaction()
    await modal.on_submit(i)
    api.update_me.assert_not_called()
    i.response.send_message.assert_awaited_once()


async def test_error_keeps_the_screen() -> None:
    api: Any = MagicMock()
    api.update_me = AsyncMock(side_effect=RuntimeError("Username já está em uso."))
    view = ConfigView(api, 123, CONTA)
    i = interaction()
    await view.save(i, {"username": "outro"})
    i.followup.send.assert_awaited_once()
    i.edit_original_response.assert_not_called()


# ------------------------------------------------------------------ /perfil proprio

async def run_perfil(bot: Any, i: Any) -> None:
    cog = ProfileCog(bot)
    callback: Any = cog.perfil.callback  # o @guarded faz o defer e trata erro
    await callback(cog, i)


async def test_own_profile_uses_the_myrank_account() -> None:
    api: Any = MagicMock()
    api.me = AsyncMock(return_value=CONTA)
    api.profile = AsyncMock(return_value=SocialProfile(1, "gui", works_count=3))
    api.social_summary = AsyncMock(return_value=SocialSummary(pending_follow_requests=2))
    bot: Any = MagicMock()
    bot.api = api
    i = interaction()
    await run_perfil(bot, i)
    api.profile.assert_awaited_once_with(123, 1)
    embed = i.followup.send.call_args.kwargs["embed"]
    assert embed.title == "gui"
    assert any(f.name == "Pedidos para seguir" for f in embed.fields)


async def test_own_profile_falls_back_without_users_me() -> None:
    api: Any = MagicMock()
    api.me = AsyncMock(side_effect=ApiUnavailableError("x"))
    api.list_works = AsyncMock(return_value=[])
    api.get_badges = AsyncMock(return_value=[])
    bot: Any = MagicMock()
    bot.api = api
    i = interaction()
    await run_perfil(bot, i)
    assert i.followup.send.call_args.kwargs["embed"].title == "Gui"


async def test_client_account_routes(make_client: ClientFactory) -> None:
    seen: list[tuple[str, str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path,
                     json.loads(request.content) if request.content else None))
        return httpx.Response(200, json={"id": 1, "username": "gui", "isPublic": True,
                                         "mutedNotifications": ["takes"]})

    client = await make_client(handler)
    account = await client.me(1)
    assert account.is_public and account.muted_notifications == ("TAKES",)
    await client.update_me(1, {"language": "EN"})
    assert seen == [("GET", "/api/users/me", None), ("PUT", "/api/users/me", {"language": "EN"})]
