from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrank.errors import ApiUnavailableError
from myrank.models import ExternalDetails, Work
from ui.modals import EditScoreModal, ScoreModal
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
            ScoreModal(api, ExternalDetails("1", "Teste", 120), 1)
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
    modal = ScoreModal(api, ExternalDetails("1", "Teste", 120), 1)
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
    modal = ScoreModal(MagicMock(), ExternalDetails("1", "Teste", 120), 1)
    await modal.on_error(interaction, RuntimeError("test"))
    if acknowledged:
        interaction.followup.send.assert_awaited_once()
        interaction.response.send_message.assert_not_awaited()
    else:
        interaction.response.send_message.assert_awaited_once()
        interaction.followup.send.assert_not_awaited()
