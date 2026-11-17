"""Modais que pedem a nota: unico dado que o usuario realmente digita.

`ScoreModal` (criar, no /add) e `EditScoreModal` (editar, no /manage) so diferem em
que dado extra guardam e em qual chamada da API fazem no submit -- o resto (parsear
a nota, tratar erro) e compartilhado em `_ScoreModal`.
"""

from __future__ import annotations

import logging
from datetime import date

import discord

from myrank.api import MyRankClient
from myrank.media import (
    MediaType,
    manual_work_payload,
    new_work_payload,
    template_label,
    template_time_weighted,
)
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

    def _extra_error(self) -> str | None:
        """Outro campo do modal invalido? Devolve a mensagem para a pessoa."""
        return None

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

        extra_error = self._extra_error()
        if extra_error is not None:
            await interaction.response.send_message(extra_error, ephemeral=True)
            return

        # Confirma antes da chamada HTTP para nao expirar a interacao.
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            work = await self._save(interaction.user.id, score)
        except Exception as exc:
            await interaction.edit_original_response(embed=to_embed(exc))
            return

        await interaction.edit_original_response(embed=self._success_embed(work))

    async def on_error(  # type: ignore[override]  # Modal.on_error e 2-arg, BaseView.on_error e 3-arg
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.exception("Erro nao tratado em %s", type(self).__name__)
        if interaction.response.is_done():
            await interaction.followup.send(embed=to_embed(error), ephemeral=True)
        else:
            await interaction.response.send_message(embed=to_embed(error), ephemeral=True)


class ScoreModal(_ScoreModal):
    """Nota de uma obra nova, vinda do fluxo de busca externa do /add.

    Quando a busca nao trouxe o tempo e o tipo usa a nota ponderada pelo tempo,
    o modal pergunta tambem as horas (opcional), como o site destaca o campo.
    """

    def __init__(
        self,
        api: MyRankClient,
        media: MediaType,
        details: ExternalDetails,
        category_id: int,
        subcategory_id: int | None = None,
    ) -> None:
        super().__init__(api, f"Nota para {details.title}")
        self._media = media
        self._details = details
        self._category_id = category_id
        self._subcategory_id = subcategory_id
        self.hours: discord.ui.TextInput[_ScoreModal] | None = None
        if media.time_weighted and not details.time_minutes:
            self.hours = discord.ui.TextInput(
                label="Quanto tempo levou? (horas, opcional)",
                placeholder="12",
                required=False,
                max_length=7,
            )
            self.add_item(self.hours)

    def _extra_error(self) -> str | None:
        if self.hours is not None and parse_hours(self.hours.value) is None:
            return "Tempo invalido -- use um numero de horas, como 12 ou 1,5."
        return None

    async def _save(self, discord_id: int, score: float) -> Work:
        time_minutes = parse_hours(self.hours.value) if self.hours is not None else None
        payload = new_work_payload(
            self._media,
            self._details,
            category_id=self._category_id,
            subcategory_id=self._subcategory_id,
            score=score,
            time_minutes=time_minutes or None,
        )
        return await self._api.create_work(discord_id, payload)

    def _success_embed(self, work: Work) -> discord.Embed:
        return embeds.work_added(work)


class EditScoreModal(_ScoreModal):
    """Nova nota de uma obra que ja existe, a partir do /manage."""

    def __init__(self, api: MyRankClient, work: Work) -> None:
        super().__init__(api, f"Editar nota de {work.title}", default_score=f"{work.score:.1f}")
        self._work = work

    async def _save(self, discord_id: int, score: float) -> Work:
        # PUT /works e parcial (campo ausente = nao mexe): mandar so a nota evita
        # sobrescrever a ficha, a subcategoria ou o template sem querer.
        return await self._api.update_work(discord_id, self._work.id, {"score": score})

    def _success_embed(self, work: Work) -> discord.Embed:
        return embeds.work_updated(work)


class ManualWorkModal(_ScoreModal):
    """Obra digitada a mao: o que nao existe em nenhuma API, ou tabela Personalizado.

    O modal do Discord aceita no maximo 5 campos: titulo, nota, criador, lancamento
    e, quando o tipo usa a nota ponderada pelo tempo, as horas.
    """

    def __init__(
        self, api: MyRankClient, template: str, category_id: int, subcategory_id: int | None,
    ) -> None:
        super().__init__(api, f"Nova obra ({template_label(template)})")
        self._template = template
        self._category_id = category_id
        self._subcategory_id = subcategory_id

        # Titulo vem antes da nota: tira a nota que a base adicionou e poe de volta.
        self.remove_item(self.score)
        self.work_title: discord.ui.TextInput[_ScoreModal] = discord.ui.TextInput(
            label="Titulo", max_length=300
        )
        self.add_item(self.work_title)
        self.add_item(self.score)
        self.creator: discord.ui.TextInput[_ScoreModal] = discord.ui.TextInput(
            label="Criador / autor (opcional)", required=False, max_length=200
        )
        self.add_item(self.creator)
        self.release: discord.ui.TextInput[_ScoreModal] = discord.ui.TextInput(
            label="Lancamento (opcional)", placeholder="2008 ou 20/01/2008",
            required=False, max_length=10,
        )
        self.add_item(self.release)
        self.hours: discord.ui.TextInput[_ScoreModal] | None = None
        if template_time_weighted(template):
            self.hours = discord.ui.TextInput(
                label="Quanto tempo levou? (horas, opcional)", placeholder="12",
                required=False, max_length=7,
            )
            self.add_item(self.hours)

    def _extra_error(self) -> str | None:
        if not self.work_title.value.strip():
            return "Informe o titulo."
        if parse_release_date(self.release.value) is INVALID:
            return "Lancamento invalido -- use o ano (2008) ou a data (20/01/2008)."
        if self.hours is not None and parse_hours(self.hours.value) is None:
            return "Tempo invalido -- use um numero de horas, como 12 ou 1,5."
        return None

    async def _save(self, discord_id: int, score: float) -> Work:
        release = parse_release_date(self.release.value)
        payload = manual_work_payload(
            self._template,
            category_id=self._category_id,
            subcategory_id=self._subcategory_id,
            title=self.work_title.value.strip(),
            score=score,
            time_minutes=(parse_hours(self.hours.value) or 0) if self.hours is not None else 0,
            creator=self.creator.value.strip() or None,
            release_date=release if isinstance(release, str) else None,
        )
        return await self._api.create_work(discord_id, payload)

    def _success_embed(self, work: Work) -> discord.Embed:
        return embeds.work_added(work)


INVALID = object()
"""Marca de valor digitado que nao da para entender (diferente de vazio)."""


def parse_release_date(raw: str) -> str | object | None:
    """Converte o lancamento digitado em data ISO.

    Ano sozinho (2008) vira 2008-01-01, como o backend faz com o Google Books;
    20/01/2008 vira 2008-01-20. Vazio vale None; o resto vale INVALID.
    """
    text = raw.strip()
    if not text:
        return None
    try:
        if len(text) == 4 and text.isdigit():
            return date(int(text), 1, 1).isoformat()
        day, month, year = text.replace("-", "/").split("/")
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return INVALID


def parse_hours(raw: str) -> int | None:
    """Horas digitadas -> minutos. Vazio vale 0 (campo opcional); invalido vale None."""
    text = raw.strip().replace(",", ".")
    if not text:
        return 0
    try:
        hours = float(text)
    except ValueError:
        return None
    if not 0 <= hours <= 10_000:  # nan e inf tambem caem aqui
        return None
    return round(hours * 60)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
