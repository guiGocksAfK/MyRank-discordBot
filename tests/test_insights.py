"""Notificacoes e IA Insights."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx

from cogs.insights import InsightsCog
from myrank.insights import Insight, Notification
from myrank.models import Work
from tests.conftest import ClientFactory
from ui.insights import (
    InsightView,
    NotificationsView,
    chat_embed,
    insight_embed,
    notifications_embed,
)
from ui.social import TextModal

INSIGHT_JSON = {
    "id": 3, "model": "gemini", "workCount": 12, "cached": False,
    "generatedAt": "2026-11-17T10:00:00", "dailyRemaining": 14, "dailyLimit": 15,
    "analysis": {
        "summaryTitle": "Fa de dramas longos", "summaryText": "Voce gosta de historias lentas.",
        "traits": [{"icon": "*", "label": "Paciente", "description": "Breaking Bad e Dark."}],
        "contradictions": [{"icon": "!", "text": "Ama terror mas deu 4 para Hereditario."}],
        "tasteProfile": [{"name": "Drama", "average": 9.1, "count": 6},
                         {"name": "Velho", "percent": 40}],
        "recommendations": [{"title": "The Wire", "year": 2002, "category": "Serie",
                             "reason": "Ritmo lento", "posterUrl": "https://img/w.jpg"},
                            {"title": "", "reason": "sem titulo e ignorada"}],
    },
    "chat": [{"role": "USER", "content": "Por que Dark?"}, {"role": "AI", "content": "Porque..."}],
}
INSIGHT = Insight.from_api(INSIGHT_JSON)


def interaction() -> Any:
    value = MagicMock()
    value.user.id = 123
    value.response.defer = AsyncMock()
    value.response.edit_message = AsyncMock()
    value.response.send_modal = AsyncMock()
    value.edit_original_response = AsyncMock()
    value.followup.send = AsyncMock()
    return value


def labels(view: discord.ui.View) -> list[str]:
    return [c.label or "" for c in view.children if isinstance(c, discord.ui.Button)]


# ------------------------------------------------------------------ notificacoes

def notification(n: int, read: bool = False) -> Notification:
    return Notification(n, "FOLLOW", read, f"Titulo {n}", "mensagem", "2026-11-16T09:00:00")


def test_notifications_embed_marks_unread() -> None:
    embed = notifications_embed([notification(1), notification(2, read=True)], 0, 1)
    lines = (embed.description or "").splitlines()
    assert lines[0].startswith("\U0001f535 **Titulo 1**") and "16/11/2026" in lines[0]
    assert lines[1].startswith("**Titulo 2**")
    assert embed.footer.text == "Pagina 1 · 1 nao lida(s)"


def test_notifications_buttons() -> None:
    cheia = NotificationsView(MagicMock(), 123, [notification(i) for i in range(10)], unread=3)
    assert not cheia.next_page.disabled and not cheia.read_all.disabled
    ultima = NotificationsView(MagicMock(), 123, [notification(1, True)], page=2, unread=0)
    assert ultima.next_page.disabled and ultima.read_all.disabled
    assert not ultima.previous_page.disabled


async def test_read_all_reloads_the_page() -> None:
    api: Any = MagicMock()
    api.read_all_notifications = AsyncMock()
    api.notifications = AsyncMock(return_value=[notification(1, True)])
    api.unread_notifications = AsyncMock(return_value=0)
    view = NotificationsView(api, 123, [notification(1)], unread=1)
    msg = MagicMock()
    msg.edit = AsyncMock()
    view.message = msg
    i = interaction()
    await view.read_all.callback(i)
    api.read_all_notifications.assert_awaited_once_with(123)
    api.notifications.assert_awaited_once_with(123, 0, 10)
    new_view = i.edit_original_response.call_args.kwargs["view"]
    assert new_view.read_all.disabled
    assert new_view.message is msg
    await new_view.on_timeout()
    assert all(c.disabled for c in new_view.children if isinstance(c, discord.ui.Button))
    msg.edit.assert_awaited_once()


# ------------------------------------------------------------------ insights

def test_insight_parse_and_embed() -> None:
    assert [r.title for r in INSIGHT.recommendations] == ["The Wire"]
    assert INSIGHT.chat[0].is_user and not INSIGHT.chat[1].is_user
    embed = insight_embed(INSIGHT)
    names = [f.name or "" for f in embed.fields]
    assert names[0] == "* Paciente"
    assert "Contradicoes" in names
    taste = next(f.value for f in embed.fields if f.name == "Perfil de gosto")
    assert taste == "Drama: media 9.1 · 6 obra(s)\nVelho: 40%"
    assert "Recomendacao: The Wire (2002) · Serie" in names
    assert embed.thumbnail.url == "https://img/w.jpg"
    assert "mensagens de IA hoje: 14/15" in (embed.footer.text or "")


def test_chat_embed_shows_last_messages() -> None:
    embed = chat_embed(INSIGHT)
    assert [f.name for f in embed.fields] == ["Voce", "IA"]


def test_regenerate_only_when_selection_is_known() -> None:
    assert "Gerar de novo" not in labels(InsightView(MagicMock(), 123, INSIGHT))
    assert "Gerar de novo" in labels(InsightView(MagicMock(), 123, INSIGHT, [1, 2]))


def test_insight_view_switches_chat_and_analysis_buttons() -> None:
    analysis_labels = labels(InsightView(MagicMock(), 123, INSIGHT))
    assert "Ver conversa" in analysis_labels and "Ver analise" not in analysis_labels
    chat_labels = labels(InsightView(MagicMock(), 123, INSIGHT, chat=True))
    assert "Ver analise" in chat_labels and "Ver conversa" not in chat_labels


async def test_insights_gerar_caps_work_ids_at_500() -> None:
    api: Any = MagicMock()
    api.list_works = AsyncMock(return_value=[Work(n, f"Obra {n}", 8.0, 8.0, 0) for n in range(505)])
    api.generate_insight = AsyncMock(return_value=INSIGHT)
    bot: Any = MagicMock()
    bot.api = api
    cog = InsightsCog(bot)
    i = interaction()
    callback: Any = cog.gerar.callback
    await callback(cog, i)
    sent_ids = api.generate_insight.call_args.args[1]
    assert len(sent_ids) == 500
    assert sent_ids[0] == 0 and sent_ids[-1] == 499


def test_no_ai_budget_disables_asking() -> None:
    sem = Insight.from_api({**INSIGHT_JSON, "dailyRemaining": 0})
    view = InsightView(MagicMock(), 123, sem, [1])
    assert view.ask.disabled and view.regenerate.disabled


async def test_ask_sends_question_and_shows_the_chat() -> None:
    api: Any = MagicMock()
    api.ask_insight = AsyncMock(return_value=INSIGHT)
    view = InsightView(api, 123, INSIGHT)
    i = interaction()
    await view.ask.callback(i)
    modal = i.response.send_modal.call_args.args[0]
    assert isinstance(modal, TextModal)
    modal.text._value = "E Dark?"
    j = interaction()
    await modal.on_submit(j)
    api.ask_insight.assert_awaited_once_with(123, 3, "E Dark?")
    assert j.edit_original_response.call_args.kwargs["embed"].title.startswith("Conversa")


async def test_regenerate_forces_refresh() -> None:
    api: Any = MagicMock()
    api.generate_insight = AsyncMock(return_value=INSIGHT)
    view = InsightView(api, 123, INSIGHT, [1, 2, 3])
    await view.regenerate.callback(interaction())
    api.generate_insight.assert_awaited_once_with(123, [1, 2, 3], refresh=True)


# ------------------------------------------------------------------ client

async def test_client_routes_and_ai_timeout(make_client: ClientFactory) -> None:
    seen: list[tuple[str, str, Any, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body, request.extensions["timeout"]))
        path = request.url.path
        if path == "/api/insights/latest":
            return httpx.Response(204)
        if path.startswith("/api/insights"):
            return httpx.Response(200, json=INSIGHT_JSON)
        if path.endswith("/unread-count"):
            return httpx.Response(200, json={"count": 4})
        if path.endswith("/read-all"):
            return httpx.Response(204)
        return httpx.Response(200, json=[{"id": 1, "type": "TAKE", "read": False,
                                          "title": "t", "message": "m"}])

    client = await make_client(handler)
    assert (await client.notifications(1, 2, 10))[0].title == "t"
    assert await client.unread_notifications(1) == 4
    await client.read_all_notifications(1)
    assert await client.latest_insight(1) is None  # 204 = nunca gerou
    await client.generate_insight(1, [5, 6], refresh=True)
    await client.ask_insight(1, 3, "oi")
    assert [(m, p, b) for m, p, b, _ in seen] == [
        ("GET", "/api/notifications", None),
        ("GET", "/api/notifications/unread-count", None),
        ("POST", "/api/notifications/read-all", None),
        ("GET", "/api/insights/latest", None),
        ("POST", "/api/insights/generate", {"workIds": [5, 6], "refresh": True}),
        ("POST", "/api/insights/3/chat", {"question": "oi"}),
    ]
    # A IA espera mais que o resto da API.
    assert seen[0][3]["read"] == 10.0
    assert seen[4][3]["read"] == 75.0
