"""Modais que pedem a nota: unico dado que o usuario realmente digita.

`ScoreModal` (criar, no /add) e `EditScoreModal` (editar, no /manage) so diferem em
que dado extra guardam e em qual chamada da API fazem no submit -- o resto (parsear
a nota, tratar erro) e compartilhado em `_ScoreModal`.
"""

from __future__ import annotations

import logging

import discord

from myrank.api import MyRankClient
from myrank.models import ExternalDetails, Work
from ui import embeds
from ui.errors import to_embed

log = logging.getLogger(__name__)


class _ScoreModal(discord.ui.Modal):
    def __init__(self, api: MyRankClient, title: str, default_score: str | None = None) -> None:
        super().__init__(title=_truncate(title, 45))
        self._api = api
        self.score: discord.ui.TextInput[_ScoreModal] = discord.ui.TextInput(
            label="Nota (0 a 10)", placeholder="8.5", default=default_score, max_length=5
        )
        self.add_item(self.score)

    async def _save(self, discord_id: int, score: float) -> Work:
        raise NotImplementedError

    def _success_embed(self, work: Work) -> discord.Embed:
        raise NotImplementedError

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            score = float(self.score.value.replace(",", "."))
        except ValueError:
            await interaction.response.send_message(
                "Nota invalida -- use um numero entre 0 e 10.", ephemeral=True
            )
            return

        if not 0.0 <= score <= 10.0:
            await interaction.response.send_message(
                "A nota tem que estar entre 0 e 10.", ephemeral=True
            )
            return

        try:
            work = await self._save(interaction.user.id, score)
        except Exception as exc:
            await interaction.response.send_message(embed=to_embed(exc), ephemeral=True)
            return

        await interaction.response.send_message(embed=self._success_embed(work))

    async def on_error(  # type: ignore[override]  # Modal.on_error e 2-arg, BaseView.on_error e 3-arg
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.exception("Erro nao tratado em %s", type(self).__name__)
        await interaction.response.send_message(embed=to_embed(error), ephemeral=True)


class ScoreModal(_ScoreModal):
    """Nota de uma obra nova, vinda do fluxo de busca externa do /add."""

    def __init__(self, api: MyRankClient, details: ExternalDetails, category_id: int) -> None:
        super().__init__(api, f"Nota para {details.title}")
        self._details = details
        self._category_id = category_id

    async def _save(self, discord_id: int, score: float) -> Work:
        # Campos aceitos por POST /works: title, score, timeMinutes, categoryId
        # (obrigatorios) + imageUrl, creator, releaseDate (opcionais). Nao ha
        # externalId no schema do backend -- so title <= 300, score 0-10, timeMinutes
        # 0-1000000 sao validados la; a nota ja foi validada aqui em cima.
        payload = {
            "title": self._details.title,
            "score": score,
            "timeMinutes": self._details.time_minutes,
            "categoryId": self._category_id,
            "imageUrl": self._details.image_url,
            "creator": self._details.creator,
            "releaseDate": self._details.release_date,
        }
        return await self._api.create_work(discord_id, payload)

    def _success_embed(self, work: Work) -> discord.Embed:
        return embeds.work_added(work)


class EditScoreModal(_ScoreModal):
    """Nova nota de uma obra que ja existe, a partir do /manage."""

    def __init__(self, api: MyRankClient, work: Work) -> None:
        super().__init__(api, f"Editar nota de {work.title}", default_score=f"{work.score:.1f}")
        self._work = work

    async def _save(self, discord_id: int, score: float) -> Work:
        payload = {
            "title": self._work.title,
            "score": score,
            "timeMinutes": self._work.time_minutes,
            "categoryId": self._work.category_id,
            "imageUrl": self._work.image_url,
            "creator": self._work.creator,
            "releaseDate": self._work.release_date,
        }
        return await self._api.update_work(discord_id, self._work.id, payload)

    def _success_embed(self, work: Work) -> discord.Embed:
        return embeds.work_updated(work)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
