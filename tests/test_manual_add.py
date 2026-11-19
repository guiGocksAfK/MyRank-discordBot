"""/add-manual: obra digitada, sem busca."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrank.models import Category, Subcategory, Work
from ui.modals import INVALID, ManualWorkModal, parse_release_date
from ui.views import ManualFlow, OpenModalView, SubcategoryPickView, TemplatePickView

FILMES = Category(1, "Filmes", templates=("movie",))
MISTA = Category(2, "Series e animes", templates=("tv", "anime"))
COM_SUBS = Category(3, "Livros", templates=("book",), subcategories=(Subcategory(8, "Ficção"),))
LUGARES = Category(4, "Lugares", templates=("custom",))


def interaction() -> Any:
    value = MagicMock()
    value.user.id = 123
    value.response.defer = AsyncMock()
    value.response.edit_message = AsyncMock()
    value.response.send_modal = AsyncMock()
    value.response.send_message = AsyncMock()
    value.edit_original_response = AsyncMock()
    return value


@pytest.mark.parametrize(
    ("table", "template", "expected"),
    [(FILMES, "movie", OpenModalView), (MISTA, None, TemplatePickView),
     (COM_SUBS, "book", SubcategoryPickView)],
)
def test_first_step_shows_only_the_real_choice(
    table: Category, template: str | None, expected: type,
) -> None:
    _, view = ManualFlow(MagicMock(), 123, table, template).first_step()
    assert isinstance(view, expected)


async def test_mixed_table_asks_type_then_opens_modal() -> None:
    flow = ManualFlow(MagicMock(), 123, MISTA, None)
    _, view = flow.first_step()
    assert [o.value for o in view.children[0].options] == ["tv", "anime"]  # type: ignore[attr-defined]
    i = interaction()
    await view._on_pick(i, "anime")  # type: ignore[attr-defined]
    modal = i.response.send_modal.call_args.args[0]
    assert isinstance(modal, ManualWorkModal)
    assert (modal._template, modal._category_id, modal._subcategory_id) == ("anime", 2, None)


def test_custom_and_music_fields() -> None:
    custom = ManualWorkModal(MagicMock(), "custom", 4, None)
    music = ManualWorkModal(MagicMock(), "music", 5, None)
    # Titulo primeiro, nota em seguida; 5 campos no maximo (limite do Discord).
    assert custom.children[:2] == [custom.work_title, custom.score]
    assert len(custom.children) == 5
    assert music.hours is None  # musica nao usa ponderacao por tempo


async def test_manual_payload() -> None:
    api: Any = MagicMock()
    api.create_work = AsyncMock(return_value=Work(1, "Ibirapuera", 9.0, 9.0, 180))
    modal = ManualWorkModal(api, "custom", 4, None)
    modal.work_title._value = "  Ibirapuera "
    modal.score._value = "9"
    modal.creator._value = ""
    modal.release._value = "2024"
    assert modal.hours is not None
    modal.hours._value = "3"
    await modal.on_submit(interaction())
    api.create_work.assert_awaited_once_with(123, {
        "categoryId": 4,
        "subcategoryId": None,
        "template": "custom",
        "title": "Ibirapuera",
        "score": 9.0,
        "timeMinutes": 180,
        "creator": None,
        "releaseDate": "2024-01-01",
    })


@pytest.mark.parametrize(
    ("field", "value"), [("work_title", "   "), ("release", "ontem"), ("release", "31/02/2020")],
)
async def test_invalid_manual_input_does_not_call_api(field: str, value: str) -> None:
    api: Any = MagicMock()
    modal = ManualWorkModal(api, "movie", 1, None)
    modal.work_title._value = "Filme"
    modal.score._value = "8"
    getattr(modal, field)._value = value
    i = interaction()
    await modal.on_submit(i)
    api.create_work.assert_not_called()
    i.response.send_message.assert_awaited_once()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", None), ("2008", "2008-01-01"), ("20/01/2008", "2008-01-20"),
     ("20-01-2008", "2008-01-20"), ("2008/01", INVALID), ("abc", INVALID)],
)
def test_parse_release_date(raw: str, expected: object) -> None:
    assert parse_release_date(raw) == expected
