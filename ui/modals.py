"""Modais: os unicos lugares em que a pessoa digita alguma coisa.

Todos seguem o mesmo roteiro em `_WorkModal`: conferir o que foi digitado (erro
volta na hora, sem chamar a API), confirmar a interacao antes da chamada HTTP,
salvar e mostrar o resultado. As subclasses so dizem que campos tem, como validar e
o que mandar.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

import discord

from myrank.api import MyRankClient
from myrank.media import (
    MediaType,
    manual_work_payload,
    new_work_payload,
    template_label,
    template_time_weighted,
)
from myrank.models import CustomField, ExternalDetails, Work
from myrank.works import custom_fields_payload, edit_payload
from ui import embeds
from ui.errors import to_embed

log = logging.getLogger(__name__)

OnSaved = Callable[[Work], Awaitable[None]]

INVALID = object()
"""Marca de valor digitado que nao da para entender (diferente de vazio)."""

TIME_ERROR = "Tempo invalido -- use um numero de horas, como 12 ou 1,5."
RELEASE_ERROR = "Lancamento invalido -- use o ano (2008) ou a data (20/01/2008)."


class _WorkModal(discord.ui.Modal):
    def __init__(self, api: MyRankClient, title: str, on_saved: OnSaved | None = None) -> None:
        super().__init__(title=_truncate(title, 45))
        self._api = api
        self._on_saved = on_saved

    def _validate(self) -> str | None:
        """Algo digitado nao serve? Devolve a mensagem para a pessoa."""
        return None

    async def _persist(self, discord_id: int) -> Work:
        raise NotImplementedError

    def _success_embed(self, work: Work) -> discord.Embed:
        raise NotImplementedError

    def _text(
        self, label: str, *, default: str | None = None, placeholder: str | None = None,
        required: bool = True, max_length: int | None = None,
    ) -> discord.ui.TextInput[_WorkModal]:
        field: discord.ui.TextInput[_WorkModal] = discord.ui.TextInput(
            label=_truncate(label, 45), default=default, placeholder=placeholder,
            required=required, max_length=max_length,
        )
        self.add_item(field)
        return field

    async def on_submit(self, interaction: discord.Interaction) -> None:
        error = self._validate()
        if error is not None:
            await interaction.response.send_message(error, ephemeral=True)
            return

        # Confirma antes da chamada HTTP para nao expirar a interacao.
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            work = await self._persist(interaction.user.id)
        except Exception as exc:
            await interaction.edit_original_response(embed=to_embed(exc))
            return

        await interaction.edit_original_response(embed=self._success_embed(work))
        if self._on_saved is not None:
            await self._on_saved(work)

    async def on_error(  # type: ignore[override]  # Modal.on_error e 2-arg, BaseView.on_error e 3-arg
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.exception("Erro nao tratado em %s", type(self).__name__)
        if interaction.response.is_done():
            await interaction.followup.send(embed=to_embed(error), ephemeral=True)
        else:
            await interaction.response.send_message(embed=to_embed(error), ephemeral=True)


class _ScoreModal(_WorkModal):
    """Modal com nota. A nota ja chega validada (0 a 10) em `_save`."""

    def __init__(
        self, api: MyRankClient, title: str, default_score: str | None = None,
        on_saved: OnSaved | None = None,
    ) -> None:
        super().__init__(api, title, on_saved)
        self._score = 0.0
        self.score = self._text("Nota (0 a 10)", placeholder="8.5", default=default_score,
                                max_length=5)

    def _extra_error(self) -> str | None:
        return None

    def _validate(self) -> str | None:
        try:
            score = float(self.score.value.replace(",", "."))
        except ValueError:
            return "Nota invalida -- use um numero entre 0 e 10."
        if not 0.0 <= score <= 10.0:  # nan tambem cai aqui
            return "A nota tem que estar entre 0 e 10."
        self._score = score
        return self._extra_error()

    async def _persist(self, discord_id: int) -> Work:
        return await self._save(discord_id, self._score)

    async def _save(self, discord_id: int, score: float) -> Work:
        raise NotImplementedError


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
        self.hours: discord.ui.TextInput[_WorkModal] | None = None
        if media.time_weighted and not details.time_minutes:
            self.hours = self._text("Quanto tempo levou? (horas, opcional)", placeholder="12",
                                    required=False, max_length=7)

    def _extra_error(self) -> str | None:
        if self.hours is not None and parse_hours(self.hours.value) is None:
            return TIME_ERROR
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

    def __init__(self, api: MyRankClient, work: Work, on_saved: OnSaved | None = None) -> None:
        super().__init__(api, f"Editar nota de {work.title}", default_score=f"{work.score:.1f}",
                         on_saved=on_saved)
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
        self.work_title = self._text("Titulo", max_length=300)
        self.add_item(self.score)
        self.creator = self._text("Criador / autor (opcional)", required=False, max_length=200)
        self.release = self._text("Lancamento (opcional)", placeholder="2008 ou 20/01/2008",
                                  required=False, max_length=10)
        self.hours: discord.ui.TextInput[_WorkModal] | None = None
        if template_time_weighted(template):
            self.hours = self._text("Quanto tempo levou? (horas, opcional)", placeholder="12",
                                    required=False, max_length=7)

    def _extra_error(self) -> str | None:
        if not self.work_title.value.strip():
            return "Informe o titulo."
        if parse_release_date(self.release.value) is INVALID:
            return RELEASE_ERROR
        if self.hours is not None and parse_hours(self.hours.value) is None:
            return TIME_ERROR
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


class EditWorkModal(_WorkModal):
    """Dados basicos da obra no /manage: titulo, criador, lancamento, tempo e capa.

    Vem preenchido com o que esta salvo; so o que a pessoa mudar e enviado.
    """

    def __init__(self, api: MyRankClient, work: Work, on_saved: OnSaved | None = None) -> None:
        super().__init__(api, f"Editar {work.title}", on_saved)
        self._work = work
        self._release: str | None = None
        self._minutes: int | None = None
        self.work_title = self._text("Titulo", default=work.title, max_length=300)
        self.creator = self._text("Criador / autor", default=work.creator, required=False,
                                  max_length=200)
        self.release = self._text(
            "Lancamento", default=format_release_date(work.release_date),
            placeholder="2008 ou 20/01/2008", required=False, max_length=10,
        )
        self.hours: discord.ui.TextInput[_WorkModal] | None = None
        if work.template is None or template_time_weighted(work.template):
            self.hours = self._text("Tempo (horas)", default=format_hours(work.time_minutes),
                                    required=False, max_length=7)
        self.image = self._text("Capa (link da imagem)", default=work.image_url,
                                placeholder="https://...", required=False, max_length=1000)

    def _validate(self) -> str | None:
        if not self.work_title.value.strip():
            return "Informe o titulo."
        release = parse_release_date(self.release.value)
        if release is INVALID:
            return RELEASE_ERROR
        self._release = release if isinstance(release, str) else None
        if self.hours is not None:
            self._minutes = parse_hours(self.hours.value)
            if self._minutes is None:
                return TIME_ERROR
        image = self.image.value.strip()
        if image and not image.startswith(("https://", "http://")):
            return "A capa precisa ser um link de imagem, comecando com https://."
        return None

    async def _persist(self, discord_id: int) -> Work:
        payload = edit_payload(
            self._work,
            title=self.work_title.value.strip(),
            creator=self.creator.value.strip(),
            release_date=self._release,
            time_minutes=self._minutes,
            image_url=self.image.value.strip(),
        )
        if not payload:
            return self._work
        return await self._api.update_work(discord_id, self._work.id, payload)

    def _success_embed(self, work: Work) -> discord.Embed:
        return embeds.work_updated(work)


class CustomFieldsModal(_WorkModal):
    """Campos proprios de uma obra Personalizado. A tabela tem no maximo 5, o mesmo
    limite de campos de um modal do Discord."""

    def __init__(
        self, api: MyRankClient, work: Work, fields: tuple[CustomField, ...],
        on_saved: OnSaved | None = None,
    ) -> None:
        super().__init__(api, f"Campos de {work.title}", on_saved)
        self._work = work
        self._fields = fields[:5]
        self._values: dict[str, Any] = {}
        current = work.details.get("fields")
        current = current if isinstance(current, dict) else {}
        self.inputs = [
            self._text(
                field.name, default=format_custom_value(field.type, current.get(field.id)),
                placeholder=CUSTOM_PLACEHOLDERS.get(field.type), required=False,
                max_length=200,
            )
            for field in self._fields
        ]

    def _validate(self) -> str | None:
        self._values = {}
        for field, text_input in zip(self._fields, self.inputs, strict=True):
            value = parse_custom_value(field.type, text_input.value)
            if value is INVALID:
                return f"**{field.name}**: {CUSTOM_ERRORS.get(field.type, 'valor invalido')}."
            self._values[field.id] = value
        return None

    async def _persist(self, discord_id: int) -> Work:
        payload = custom_fields_payload(self._work, self._values)
        return await self._api.update_work(discord_id, self._work.id, payload)

    def _success_embed(self, work: Work) -> discord.Embed:
        return embeds.work_updated(work)


# ------------------------------------------------------------------ texto <-> valor

CUSTOM_PLACEHOLDERS = {"NUMBER": "42", "DATE": "20/01/2008", "BOOLEAN": "sim ou nao"}
CUSTOM_ERRORS = {
    "NUMBER": "use um numero, como 42 ou 3,5",
    "DATE": "use uma data completa, como 20/01/2008",
    "BOOLEAN": "responda sim ou nao",
}
_YES = {"sim", "s", "yes", "y", "true", "1"}
_NO = {"nao", "não", "n", "no", "false", "0"}


def parse_custom_value(field_type: str, raw: str) -> Any:
    """Texto digitado -> valor do campo proprio, no formato que o backend aceita.
    Vazio vale None (apaga o valor); o que nao da para entender vale INVALID."""
    text = raw.strip()
    if not text:
        return None
    if field_type == "NUMBER":
        try:
            number = float(text.replace(",", "."))
        except ValueError:
            return INVALID
        if not math.isfinite(number):
            return INVALID
        return int(number) if number.is_integer() else number
    if field_type == "DATE":
        # So data completa: o backend nao aceita ano sozinho num campo proprio.
        parsed = parse_release_date(text) if len(text) != 4 else INVALID
        return INVALID if parsed is None else parsed
    if field_type == "BOOLEAN":
        lowered = text.casefold()
        if lowered in _YES:
            return True
        if lowered in _NO:
            return False
        return INVALID
    return raw.strip()[:200]


def format_custom_value(field_type: str, value: Any) -> str | None:
    if value is None:
        return None
    if field_type == "DATE":
        return format_release_date(str(value))
    if field_type == "BOOLEAN":
        return "sim" if value is True else "nao"
    if field_type == "NUMBER" and isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


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
        if len(text) == 10 and text[4] == "-":  # ja em ISO (2008-01-20)
            return date.fromisoformat(text).isoformat()
        day, month, year = text.replace("-", "/").split("/")
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return INVALID


def format_release_date(iso: str | None) -> str | None:
    """2008-01-20 -> 20/01/2008, para vir preenchido no modal."""
    if not iso:
        return None
    try:
        return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return iso


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


def format_hours(minutes: int) -> str | None:
    if not minutes:
        return None
    hours = minutes / 60
    return str(int(hours)) if hours.is_integer() else f"{hours:.2f}".rstrip("0").replace(".", ",")


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
