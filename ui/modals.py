"""Modal do /add: unico dado que o usuario realmente digita e a nota.

Tudo o mais (titulo, duracao, categoria) ja veio da busca externa ou do select
anterior -- o modal so existe porque nota e o unico campo que a API nao tem como
adivinhar.
"""

from __future__ import annotations

import logging

import discord

from myrank.api import MyRankClient
from myrank.models import ExternalDetails
from ui import embeds
from ui.errors import to_embed

log = logging.getLogger(__name__)


class ScoreModal(discord.ui.Modal):
    def __init__(self, api: MyRankClient, details: ExternalDetails, category_id: int) -> None:
        super().__init__(title=_truncate(f"Nota para {details.title}", 45))
        self._api = api
        self._details = details
        self._category_id = category_id
        self.score: discord.ui.TextInput[ScoreModal] = discord.ui.TextInput(
            label="Nota (0 a 10)", placeholder="8.5", max_length=5
        )
        self.add_item(self.score)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            score = float(self.score.value.replace(",", "."))
        except ValueError:
            await interaction.response.send_message(
                "Nota invalida -- use um numero entre 0 e 10.", ephemeral=True
            )
            return

        payload = {
            "title": self._details.title,
            "score": score,
            "timeMinutes": self._details.time_minutes,
            "categoryId": self._category_id,
            "imageUrl": self._details.image_url,
            "creator": self._details.creator,
            "releaseDate": self._details.release_date,
            "externalId": self._details.external_id,
        }
        try:
            work = await self._api.create_work(interaction.user.id, payload)
        except Exception as exc:
            await interaction.response.send_message(embed=to_embed(exc), ephemeral=True)
            return

        await interaction.response.send_message(embed=embeds.work_added(work))

    async def on_error(  # type: ignore[override]  # Modal.on_error e 2-arg, BaseView.on_error e 3-arg
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.exception("Erro nao tratado no ScoreModal")
        await interaction.response.send_message(embed=to_embed(error), ephemeral=True)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
