"""/tabela e "Trocar tipo" do /manage."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx

from myrank.models import Category, CustomField, Subcategory, Work
from myrank.works import change_template_payload
from tests.conftest import ClientFactory
from ui import embeds
from ui.tables import (
    ALL_TEMPLATES,
    CreateTableView,
    CustomFieldActions,
    CustomFieldsView,
    NameModal,
    SubcategoryActions,
    TablePanel,
    TemplatesSelect,
    fields_body,
)
from ui.views import ConfirmView, ManageView

LIVROS = Category(1, "Livros", templates=("book",))
MISTA = Category(2, "Series e animes", templates=("tv", "anime"),
                 subcategories=(Subcategory(5, "Drama"),))
CAMPOS = (CustomField("f_a", "Local", "TEXT"), CustomField("f_b", "Visita", "DATE"))
LUGARES = Category(3, "Lugares", templates=("custom",), custom_fields=CAMPOS)


def interaction(kind: discord.InteractionType = discord.InteractionType.component) -> Any:
    value = MagicMock()
    value.user.id = 123
    value.type = kind
    value.response.is_done.return_value = False
    value.response.defer = AsyncMock()
    value.response.edit_message = AsyncMock()
    value.response.send_modal = AsyncMock()
    value.response.send_message = AsyncMock()
    value.edit_original_response = AsyncMock()
    value.original_response = AsyncMock()
    return value


def labels(view: discord.ui.View) -> list[str]:
    return [c.label for c in view.children if isinstance(c, discord.ui.Button)]  # type: ignore[misc]


def test_panel_buttons_depend_on_the_table() -> None:
    assert labels(TablePanel(MagicMock(), 123, LIVROS, 0)) == [
        "Renomear", "Tipos", "Nova subcategoria", "Excluir tabela",
    ]
    assert labels(TablePanel(MagicMock(), 123, MISTA, 0)) == [
        "Renomear", "Tipos", "Nova subcategoria", "Editar subcategoria", "Excluir tabela",
    ]
    assert "Campos proprios" in labels(TablePanel(MagicMock(), 123, LUGARES, 0))


async def test_templates_select_keeps_the_site_order() -> None:
    picked = AsyncMock()
    select = TemplatesSelect(("anime",), picked)
    assert [o.value for o in select.options] == list(ALL_TEMPLATES)
    assert [o.default for o in select.options if o.value == "anime"] == [True]
    select._values = ["custom", "movie"]
    await select.callback(interaction())
    assert picked.call_args.args[1] == ["movie", "custom"]


async def test_create_table() -> None:
    api: Any = MagicMock()
    api.create_category = AsyncMock(return_value=LIVROS)
    view = CreateTableView(api, 123, "Livros")
    i = interaction()
    await view._on_pick(i, ["book"])
    api.create_category.assert_awaited_once_with(123, "Livros", ["book"])
    assert i.edit_original_response.call_args.kwargs["embed"].title == "Tabela criada: Livros"


async def test_rename_reloads_the_panel() -> None:
    api: Any = MagicMock()
    api.update_category = AsyncMock()
    api.get_categories = AsyncMock(return_value=[Category(1, "Leituras", templates=("book",))])
    api.list_works = AsyncMock(return_value=[MagicMock(), MagicMock()])
    panel = TablePanel(api, 123, LIVROS, 0)
    panel.message = MagicMock()
    panel.message.edit = AsyncMock()
    i = interaction()
    await panel.rename.callback(i)
    modal = i.response.send_modal.call_args.args[0]
    assert isinstance(modal, NameModal) and modal.name.default == "Livros"
    modal.name._value = " Leituras "
    await modal.on_submit(interaction(discord.InteractionType.modal_submit))
    api.update_category.assert_awaited_once_with(123, 1, name="Leituras")
    new_panel = panel.message.edit.call_args.kwargs["view"]
    assert isinstance(new_panel, TablePanel)
    assert (new_panel.table.name, new_panel.work_count) == ("Leituras", 2)


async def test_backend_error_is_shown_and_panel_kept() -> None:
    api: Any = MagicMock()
    api.update_category = AsyncMock(side_effect=RuntimeError("tipo em uso"))
    panel = TablePanel(api, 123, MISTA, 0)
    panel.message = MagicMock()
    panel.message.edit = AsyncMock()
    i = interaction()
    await panel.types.callback(i)
    select = i.response.send_message.call_args.kwargs["view"].children[0]
    j = interaction()
    await select._on_pick(j, ["tv"])
    assert j.edit_original_response.call_args.kwargs["embed"] is not None
    panel.message.edit.assert_not_called()


async def test_delete_table_warns_how_many_works_go_with_it() -> None:
    api: Any = MagicMock()
    api.delete_category = AsyncMock()
    panel = TablePanel(api, 123, LIVROS, 12)
    i = interaction()
    await panel.delete.callback(i)
    kwargs = i.response.edit_message.call_args.kwargs
    assert "12 obras" in kwargs["content"]
    assert isinstance(kwargs["view"], ConfirmView)
    api.delete_category.assert_not_called()
    await kwargs["view"]._on_confirm(interaction())
    api.delete_category.assert_awaited_once_with(123, 1)


def test_delete_warning_singular() -> None:
    assert "**1 obra**" in embeds.delete_table_warning(LIVROS, 1)


async def test_delete_subcategory_keeps_the_works() -> None:
    api: Any = MagicMock()
    api.delete_subcategory = AsyncMock()
    panel = TablePanel(api, 123, MISTA, 0)
    actions = SubcategoryActions(panel, 5, "Drama")
    i = interaction()
    await actions.delete.callback(i)
    assert "continuam na tabela" in i.response.edit_message.call_args.kwargs["content"]
    await i.response.edit_message.call_args.kwargs["view"]._on_confirm(interaction())
    api.delete_subcategory.assert_awaited_once_with(123, 2, 5)


# ------------------------------------------------------------------ campos proprios

async def test_new_custom_field_sends_the_full_list() -> None:
    api: Any = MagicMock()
    api.set_custom_fields = AsyncMock()
    panel = TablePanel(api, 123, LUGARES, 0)
    view = CustomFieldsView(panel)
    i = interaction()
    await view._type_picked(i, "BOOLEAN")
    modal = i.response.send_modal.call_args.args[0]
    modal.name._value = "Volto?"
    await modal.on_submit(interaction(discord.InteractionType.modal_submit))
    api.set_custom_fields.assert_awaited_once_with(123, 3, [
        {"id": "f_a", "name": "Local", "type": "TEXT"},
        {"id": "f_b", "name": "Visita", "type": "DATE"},
        {"name": "Volto?", "type": "BOOLEAN"},
    ])


def test_no_new_field_after_five() -> None:
    cheia = Category(4, "Cheia", templates=("custom",), custom_fields=tuple(
        CustomField(f"f_{n}", f"C{n}", "TEXT") for n in range(5)
    ))
    assert "Novo campo" not in labels(CustomFieldsView(TablePanel(MagicMock(), 123, cheia, 0)))


async def test_rename_and_delete_custom_field() -> None:
    api: Any = MagicMock()
    api.set_custom_fields = AsyncMock()
    panel = TablePanel(api, 123, LUGARES, 0)
    actions = CustomFieldActions(panel, CAMPOS[0])

    i = interaction()
    await actions.rename.callback(i)
    modal = i.response.send_modal.call_args.args[0]
    modal.name._value = "Cidade"
    await modal.on_submit(interaction(discord.InteractionType.modal_submit))
    assert api.set_custom_fields.call_args.args[2] == [
        {"id": "f_a", "name": "Cidade", "type": "TEXT"},
        {"id": "f_b", "name": "Visita", "type": "DATE"},
    ]

    j = interaction()
    await actions.delete.callback(j)
    assert "todas as obras" in j.response.edit_message.call_args.kwargs["content"]
    await j.response.edit_message.call_args.kwargs["view"]._on_confirm(interaction())
    assert api.set_custom_fields.call_args.args[2] == fields_body((CAMPOS[1],))


# ------------------------------------------------------------------ trocar tipo da obra

def test_change_template_drops_old_search_link_and_fields() -> None:
    work = Work(1, "X", 8, 8, 0, 2, template="tv", details={
        "externalId": "9", "provider": "tmdb", "fields": {}, "genres": ["Drama"],
    })
    assert change_template_payload(work, "anime") == {
        "template": "anime", "details": {"genres": ["Drama"]},
    }


async def test_change_type_only_in_mixed_tables() -> None:
    work = Work(1, "X", 8, 8, 0, 2, template="tv")
    assert "Trocar tipo" not in labels(ManageView(MagicMock(), 123, work, LIVROS))
    api: Any = MagicMock()
    api.update_work = AsyncMock(return_value=Work(1, "X", 8, 8, 0, 2, template="anime"))
    panel = ManageView(api, 123, work, MISTA)
    i = interaction()
    await panel.change_type.callback(i)
    select = i.response.send_message.call_args.kwargs["view"].children[0]
    assert [o.value for o in select.options] == ["anime"]
    await panel._type_picked(interaction(), "anime")
    api.update_work.assert_awaited_once_with(123, 1, {"template": "anime", "details": {}})


# ------------------------------------------------------------------ client

async def test_client_table_routes(make_client: ClientFactory) -> None:
    seen: list[tuple[str, str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": 1, "name": "Livros", "templates": ["book"]})

    client = await make_client(handler)
    await client.create_category(1, "Livros", ["book"])
    await client.update_category(1, 1, templates=["book", "manga"])
    await client.set_custom_fields(1, 1, [])
    await client.create_subcategory(1, 1, "Ficção")
    await client.rename_subcategory(1, 1, 5, "Fantasia")
    await client.delete_subcategory(1, 1, 5)
    await client.delete_category(1, 1)
    assert seen == [
        ("POST", "/api/categories", {"name": "Livros", "templates": ["book"]}),
        ("PUT", "/api/categories/1", {"templates": ["book", "manga"]}),
        ("PUT", "/api/categories/1/custom-fields", []),
        ("POST", "/api/categories/1/subcategories", {"name": "Ficção"}),
        ("PUT", "/api/categories/1/subcategories/5", {"name": "Fantasia"}),
        ("DELETE", "/api/categories/1/subcategories/5", None),
        ("DELETE", "/api/categories/1", None),
    ]
