"""/manage: editar dados, campos proprios, subcategoria e "Atualizar dados"."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from myrank.media import TV
from myrank.models import Category, CustomField, ExternalDetails, ExternalResult, Subcategory, Work
from myrank.works import edit_payload, refresh_payload
from ui import embeds
from ui.modals import (
    INVALID,
    CustomFieldsModal,
    EditWorkModal,
    format_hours,
    format_release_date,
    parse_custom_value,
)
from ui.views import ManageView, RefreshPickView, SubcategoryMoveView

SERIE = Work(
    7, "Breaking Bad", 9.0, 9.5, 3000, 2, "Series", "https://img/bb.jpg", "Vince Gilligan",
    "2008-01-20", template="tv", subcategory_id=5, subcategory_name="Drama",
    details={"seasons": 5, "externalId": "1396", "provider": "tmdb"},
)
TABELA_SERIES = Category(2, "Series", templates=("tv",), subcategories=(Subcategory(5, "Drama"),))
CAMPOS = (CustomField("f_local", "Local", "TEXT"), CustomField("f_nota", "Estrelas", "NUMBER"),
          CustomField("f_dia", "Visita", "DATE"), CustomField("f_volto", "Volto?", "BOOLEAN"))
LUGARES = Category(4, "Lugares", templates=("custom",), custom_fields=CAMPOS)
PRACA = Work(9, "Praça", 8.0, 8.0, 0, 4, template="custom",
             details={"fields": {"f_local": "SP"}, "outro": 1})


def interaction() -> Any:
    value = MagicMock()
    value.user.id = 123
    value.response.defer = AsyncMock()
    value.response.send_modal = AsyncMock()
    value.response.send_message = AsyncMock()
    value.edit_original_response = AsyncMock()
    return value


def buttons(view: ManageView) -> list[str]:
    return [child.label for child in view.children]  # type: ignore[attr-defined]


def test_buttons_depend_on_the_work() -> None:
    assert buttons(ManageView(MagicMock(), 123, SERIE, TABELA_SERIES)) == [
        "Editar nota", "Editar dados", "Subcategoria", "Atualizar dados", "Remover",
    ]
    assert buttons(ManageView(MagicMock(), 123, PRACA, LUGARES)) == [
        "Editar nota", "Editar dados", "Campos proprios", "Remover",
    ]


# ------------------------------------------------------------------ editar dados

def test_edit_payload_sends_only_what_changed() -> None:
    same = edit_payload(SERIE, title="Breaking Bad", creator="Vince Gilligan",
                        release_date="2008-01-20", time_minutes=3000, image_url="https://img/bb.jpg")
    assert same == {}
    changed = edit_payload(SERIE, title="BB", creator="", release_date=None,
                           time_minutes=None, image_url="")
    # Criador e capa vazios apagam; data vazia e tempo nao perguntado nao mandam nada.
    assert changed == {"title": "BB", "creator": "", "imageUrl": ""}


async def test_edit_modal_comes_filled_and_saves_the_diff() -> None:
    api: Any = MagicMock()
    api.update_work = AsyncMock(return_value=SERIE)
    on_saved = AsyncMock()
    modal = EditWorkModal(api, SERIE, on_saved=on_saved)
    assert modal.release.default == "20/01/2008"
    assert modal.hours is not None and modal.hours.default == "50"
    for field in (modal.work_title, modal.creator, modal.release, modal.hours, modal.image):
        field._value = field.default or ""
    modal.hours._value = "52,5"
    await modal.on_submit(interaction())
    api.update_work.assert_awaited_once_with(123, 7, {"timeMinutes": 3150})
    on_saved.assert_awaited_once_with(SERIE)


async def test_edit_modal_without_changes_does_not_call_api() -> None:
    api: Any = MagicMock()
    modal = EditWorkModal(api, SERIE)
    for field in (modal.work_title, modal.creator, modal.release, modal.hours, modal.image):
        assert field is not None
        field._value = field.default or ""
    await modal.on_submit(interaction())
    api.update_work.assert_not_called()


async def test_edit_modal_rejects_cover_that_is_not_a_link() -> None:
    api: Any = MagicMock()
    modal = EditWorkModal(api, SERIE)
    for field in (modal.work_title, modal.creator, modal.release, modal.hours, modal.image):
        assert field is not None
        field._value = field.default or ""
    modal.image._value = "capa.jpg"
    i = interaction()
    await modal.on_submit(i)
    api.update_work.assert_not_called()
    i.response.send_message.assert_awaited_once()


@pytest.mark.parametrize(("minutes", "text"), [(0, None), (120, "2"), (90, "1,5")])
def test_format_hours(minutes: int, text: str | None) -> None:
    assert format_hours(minutes) == text


def test_format_release_date() -> None:
    assert format_release_date("2008-01-20") == "20/01/2008"
    assert format_release_date(None) is None


# ------------------------------------------------------------------ campos proprios

@pytest.mark.parametrize(
    ("kind", "raw", "value"),
    [("TEXT", " SP ", "SP"), ("TEXT", "", None), ("NUMBER", "3,5", 3.5), ("NUMBER", "4", 4),
     ("NUMBER", "inf", INVALID), ("NUMBER", "x", INVALID), ("DATE", "20/01/2008", "2008-01-20"),
     ("DATE", "2008", INVALID), ("BOOLEAN", "Sim", True), ("BOOLEAN", "não", False),
     ("BOOLEAN", "talvez", INVALID)],
)
def test_parse_custom_value(kind: str, raw: str, value: object) -> None:
    assert parse_custom_value(kind, raw) == value


async def test_custom_fields_replace_only_fields_inside_details() -> None:
    api: Any = MagicMock()
    api.update_work = AsyncMock(return_value=PRACA)
    modal = CustomFieldsModal(api, PRACA, CAMPOS)
    assert [f.default for f in modal.inputs] == ["SP", None, None, None]
    modal.inputs[0]._value = ""
    modal.inputs[1]._value = "5"
    modal.inputs[2]._value = "01/10/2026"
    modal.inputs[3]._value = "sim"
    await modal.on_submit(interaction())
    api.update_work.assert_awaited_once_with(123, 9, {"details": {
        "outro": 1,
        "fields": {"f_local": None, "f_nota": 5, "f_dia": "2026-10-01", "f_volto": True},
    }})


async def test_invalid_custom_field_names_the_field() -> None:
    api: Any = MagicMock()
    modal = CustomFieldsModal(api, PRACA, CAMPOS)
    for text_input in modal.inputs:
        text_input._value = ""
    modal.inputs[3]._value = "talvez"
    i = interaction()
    await modal.on_submit(i)
    api.update_work.assert_not_called()
    assert "Volto?" in i.response.send_message.call_args.args[0]


# ------------------------------------------------------------------ subcategoria

@pytest.mark.parametrize(("value", "sent"), [("0", 0), ("5", 5)])
async def test_move_subcategory(value: str, sent: int) -> None:
    api: Any = MagicMock()
    api.update_work = AsyncMock(return_value=SERIE)
    panel = ManageView(api, 123, SERIE, TABELA_SERIES)
    panel.saved = AsyncMock()  # type: ignore[method-assign]
    view = SubcategoryMoveView(panel, TABELA_SERIES)
    options = view.children[0].options  # type: ignore[attr-defined]
    assert [o.default for o in options] == [False, True]  # a atual vem marcada
    await view._on_pick(interaction(), value)
    api.update_work.assert_awaited_once_with(123, 7, {"subcategoryId": sent})
    panel.saved.assert_awaited_once_with(SERIE)


# ------------------------------------------------------------------ atualizar dados

def test_refresh_payload_like_the_site() -> None:
    fetched = ExternalDetails("1396", "Outro titulo", 9999, "https://img/novo.jpg", "Outro",
                              "2000-01-01", {"seasons": 6, "status": "Ended"})
    payload = refresh_payload(SERIE, TV, fetched)
    # Titulo, tempo, criador, capa e data (ja preenchidas) ficam como estao.
    assert payload == {"details": {
        "seasons": 6, "status": "Ended", "externalId": "1396", "provider": "tmdb",
    }}
    vazia = Work(1, "X", 5, 5, 0, template="tv")
    assert refresh_payload(vazia, TV, fetched)["imageUrl"] == "https://img/novo.jpg"
    assert refresh_payload(vazia, TV, fetched)["releaseDate"] == "2000-01-01"


async def test_refresh_with_known_id_goes_straight_to_the_source() -> None:
    api: Any = MagicMock()
    api.external_details = AsyncMock(return_value=ExternalDetails("1396", "BB", 0))
    api.update_work = AsyncMock(return_value=SERIE)
    panel = ManageView(api, 123, SERIE, TABELA_SERIES)
    await panel.refresh.callback(interaction())
    api.external_details.assert_awaited_once_with(123, "tv", "1396")
    api.external_search.assert_not_called()
    api.update_work.assert_awaited_once()


async def test_refresh_without_id_asks_which_result() -> None:
    api: Any = MagicMock()
    api.external_search = AsyncMock(return_value=[ExternalResult("1", "Velha", "1990")])
    api.external_details = AsyncMock(return_value=ExternalDetails("1", "Velha", 0))
    api.update_work = AsyncMock(return_value=SERIE)
    velha = Work(3, "Velha", 7, 7, 0, 2, template="tv")
    panel = ManageView(api, 123, velha, TABELA_SERIES)
    i = interaction()
    await panel.refresh.callback(i)
    api.external_search.assert_awaited_once_with(123, "tv", "Velha")
    api.update_work.assert_not_called()
    pick = i.edit_original_response.call_args.kwargs["view"]
    assert isinstance(pick, RefreshPickView)
    await pick._on_pick(interaction(), "1")
    api.external_details.assert_awaited_once_with(123, "tv", "1")
    payload = api.update_work.call_args.args[2]
    assert payload["details"]["externalId"] == "1"


def test_embeds_respect_discord_limits_and_empty_custom_fields() -> None:
    long_title = "A" * 300
    assert len(embeds.base(long_title).title or "") == 256
    work = Work(1, long_title, 9.0, 9.5, 60, position=1)
    ranking = embeds.ranking([work], 0, 1, 1, "Categoria")
    assert len(ranking.fields[0].name or "") == 256

    tabela = Category(
        4, "Lugares", templates=("custom",),
        custom_fields=(
            CustomField("f_vazio", "Vazio", "TEXT"),
            CustomField("f_zero", "Zero", "NUMBER"),
            CustomField("f_nao", "Volto?", "BOOLEAN"),
        ),
    )
    obra = Work(
        2, "Lugar", 8.0, 8.0, 0, 4, template="custom",
        details={"fields": {"f_vazio": "", "f_zero": 0, "f_nao": False}},
    )
    detail = embeds.work_detail(obra, tabela)
    fields = {f.name: f.value for f in detail.fields}
    assert "Vazio" not in fields
    assert fields["Zero"] == "0"
    assert fields["Volto?"] == "Nao"


async def test_manage_saved_ignores_discord_http_error() -> None:
    panel = ManageView(MagicMock(), 123, SERIE, TABELA_SERIES)
    panel.message = MagicMock()
    response = MagicMock(status=404, reason="Not Found")
    panel.message.edit = AsyncMock(side_effect=discord.HTTPException(response, "Unknown Message"))
    await panel.saved(SERIE)
    panel.message.edit.assert_awaited_once()


def test_non_http_cover_urls_are_ignored_in_embeds() -> None:
    work = Work(1, "Capa Data", 8.0, 8.0, 0, image_url="data:image/png;base64,abc")
    assert not embeds.work_detail(work).thumbnail.url
    assert not embeds.profile("Gui", "data:image/png;base64,abc", 1, 8.0, 0, 1).thumbnail.url
