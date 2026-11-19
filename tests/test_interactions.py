from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrank.errors import ApiUnavailableError
from myrank.media import GAME, TV
from myrank.models import ExternalDetails, Work
from ui.modals import EditScoreModal, ScoreModal, parse_hours
from ui.views import ManageView


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
@pytest.mark.parametrize("failed", [False, True])
async def test_pending_api_is_acknowledged(operation: str, failed: bool) -> None:
    """A API pode ficar pendente sem consumir a janela da resposta inicial."""
    entered = asyncio.Event()
    release = asyncio.Event()
    work = Work(1, "Teste", 8.5, 8.5, 120, 1)
    interaction: Any = MagicMock()
    interaction.user.id = 123
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.edit_original_response = AsyncMock()

    async def request(*args: Any) -> Work:
        entered.set()
        await release.wait()
        if failed:
            raise ApiUnavailableError("Indisponivel")
        return work

    api: Any = MagicMock()
    method = AsyncMock(side_effect=request)
    setattr(api, operation + "_work", method)
    if operation == "delete":
        callback = ManageView(api, 123, work)._confirm_remove(interaction)
    else:
        modal = (
            ScoreModal(api, TV, ExternalDetails("1", "Teste", 120), 1)
            if operation == "create" else EditScoreModal(api, work)
        )
        modal.score._value = "8,5"
        callback = modal.on_submit(interaction)

    task = asyncio.create_task(callback)
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        interaction.response.defer.assert_awaited_once()
        interaction.edit_original_response.assert_not_awaited()
    finally:
        release.set()
        await task

    interaction.edit_original_response.assert_awaited_once()
    interaction.response.send_message.assert_not_awaited()
    interaction.response.edit_message.assert_not_awaited()
    assert method.call_args.args[0] == 123
    if operation == "delete":
        method.assert_awaited_once_with(123, 1)
    else:
        assert method.call_args.args[-1]["score"] == 8.5
    if failed:
        assert "Indisponivel" in interaction.edit_original_response.call_args.kwargs[
            "embed"
        ].description


@pytest.mark.parametrize("value", ["abc", "-1", "11", "nan", "inf"])
async def test_invalid_score_does_not_call_api(value: str) -> None:
    api: Any = MagicMock()
    interaction: Any = MagicMock()
    interaction.response.send_message = AsyncMock()
    modal = ScoreModal(api, TV, ExternalDetails("1", "Teste", 120), 1)
    modal.score._value = value
    await modal.on_submit(interaction)
    api.create_work.assert_not_called()
    interaction.response.defer.assert_not_called()
    interaction.response.send_message.assert_awaited_once()


@pytest.mark.parametrize("acknowledged", [False, True])
async def test_modal_error_uses_available_response(acknowledged: bool) -> None:
    interaction: Any = MagicMock()
    interaction.response.is_done.return_value = acknowledged
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    modal = ScoreModal(MagicMock(), TV, ExternalDetails("1", "Teste", 120), 1)
    await modal.on_error(interaction, RuntimeError("test"))
    if acknowledged:
        interaction.followup.send.assert_awaited_once()
        interaction.response.send_message.assert_not_awaited()
    else:
        interaction.response.send_message.assert_awaited_once()
        interaction.followup.send.assert_not_awaited()


async def test_edit_sends_only_the_score() -> None:
    """PUT parcial: mandar so a nota nao apaga ficha, subcategoria nem template."""
    api: Any = MagicMock()
    api.update_work = AsyncMock(return_value=Work(1, "Teste", 7.0, 7.0, 0))
    interaction: Any = MagicMock()
    interaction.user.id = 123
    interaction.response.defer = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    modal = EditScoreModal(api, Work(1, "Teste", 8.0, 8.0, 0, details={"seasons": 5}))
    modal.score._value = "7"
    await modal.on_submit(interaction)
    api.update_work.assert_awaited_once_with(123, 1, {"score": 7.0})


async def test_asks_hours_only_when_search_had_no_time() -> None:
    with_time = ScoreModal(MagicMock(), GAME, ExternalDetails("1", "Jogo", 600), 1)
    without_time = ScoreModal(MagicMock(), GAME, ExternalDetails("1", "Jogo", 0), 1)
    assert with_time.hours is None
    assert without_time.hours is not None


async def test_hours_typed_become_minutes_in_the_payload() -> None:
    api: Any = MagicMock()
    api.create_work = AsyncMock(return_value=Work(1, "Jogo", 9.0, 9.0, 90))
    interaction: Any = MagicMock()
    interaction.user.id = 123
    interaction.response.defer = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    modal = ScoreModal(api, GAME, ExternalDetails("3498", "Jogo", 0), 4, 9)
    modal.score._value = "9"
    assert modal.hours is not None
    modal.hours._value = "1,5"
    await modal.on_submit(interaction)
    payload = api.create_work.call_args.args[1]
    assert payload["timeMinutes"] == 90
    assert payload["subcategoryId"] == 9
    assert payload["details"] == {"provider": "rawg", "externalId": "3498"}


@pytest.mark.parametrize(
    ("raw", "minutes"),
    [("", 0), ("2", 120), ("0,5", 30), ("abc", None), ("-1", None), ("nan", None)],
)
def test_parse_hours(raw: str, minutes: int | None) -> None:
    assert parse_hours(raw) == minutes


async def test_invalid_hours_do_not_call_api() -> None:
    api: Any = MagicMock()
    interaction: Any = MagicMock()
    interaction.response.send_message = AsyncMock()
    modal = ScoreModal(api, GAME, ExternalDetails("1", "Jogo", 0), 1)
    modal.score._value = "8"
    assert modal.hours is not None
    modal.hours._value = "muito"
    await modal.on_submit(interaction)
    api.create_work.assert_not_called()
    interaction.response.send_message.assert_awaited_once()
