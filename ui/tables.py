"""Telas do /tabela: criar tabela e o painel de uma tabela.

O painel mostra so os botoes que fazem sentido para a tabela (campos proprios so em
Personalizado, editar subcategoria so se houver alguma). Depois de cada mudanca ele
busca a tabela de novo no backend e se redesenha -- nada e calculado aqui.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

from myrank.api import MyRankClient
from myrank.media import CUSTOM_TEMPLATE, MEDIA_TYPES, template_label
from myrank.models import Category, CustomField
from ui import embeds
from ui.errors import to_embed
from ui.views import ChoiceSelect, ConfirmView, _check_author, _disable_on_timeout, _truncate

ALL_TEMPLATES: tuple[str, ...] = (*(m.template for m in MEDIA_TYPES), CUSTOM_TEMPLATE)
MAX_CUSTOM_FIELDS = 5
FIELD_TYPES = (("TEXT", "Texto"), ("NUMBER", "Numero"), ("DATE", "Data"), ("BOOLEAN", "Sim/nao"))
FIELD_TYPE_LABELS = dict(FIELD_TYPES)

NameAction = Callable[[discord.Interaction, str], Awaitable[None]]


class TemplatesSelect(discord.ui.Select[discord.ui.View]):
    """Escolha de um ou mais tipos, na ordem da lista (o backend guarda a ordem)."""

    def __init__(
        self, selected: tuple[str, ...],
        on_pick: Callable[[discord.Interaction, list[str]], Awaitable[None]],
    ) -> None:
        options = [
            discord.SelectOption(label=template_label(t), value=t, default=t in selected)
            for t in ALL_TEMPLATES
        ]
        super().__init__(
            placeholder="Que tipos de obra entram nela?", options=options,
            min_values=1, max_values=len(options),
        )
        self._on_pick = on_pick

    async def callback(self, interaction: discord.Interaction) -> None:
        # Mantem a ordem da lista, nao a ordem de clique.
        chosen = [t for t in ALL_TEMPLATES if t in self.values]
        await self._on_pick(interaction, chosen)


class NameModal(discord.ui.Modal):
    """Um campo de nome so. Quem chama decide o que fazer com ele."""

    def __init__(
        self, title: str, label: str, action: NameAction, *,
        default: str | None = None, max_length: int = 60,
    ) -> None:
        super().__init__(title=_truncate(title, 45))
        self._action = action
        self.name: discord.ui.TextInput[NameModal] = discord.ui.TextInput(
            label=label, default=default[:max_length] if default else None, max_length=max_length
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name.value.strip()
        if not name:
            await interaction.response.send_message("O nome nao pode ficar vazio.", ephemeral=True)
            return
        await self._action(interaction, name)


async def _run(
    interaction: discord.Interaction, action: Callable[[], Awaitable[object]], done: str,
    panel: TablePanel | None,
) -> None:
    """Roteiro de toda mudanca: confirmar a interacao, chamar a API, avisar e
    redesenhar o painel. Erro do backend (nome repetido, tipo em uso...) vira a
    mensagem dele."""
    if not interaction.response.is_done():
        if interaction.type == discord.InteractionType.component:
            # Clique num botao/select: a resposta substitui a propria mensagem.
            await interaction.response.defer()
        else:
            # Modal: a resposta e uma mensagem nova, so para a pessoa.
            await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        await action()
    except Exception as exc:
        await interaction.edit_original_response(content=None, embed=to_embed(exc), view=None)
        return
    await interaction.edit_original_response(content=done, embed=None, view=None)
    if panel is not None:
        await panel.reload(interaction.user.id)


# ------------------------------------------------------------------ criar

class CreateTableView(discord.ui.View):
    def __init__(self, api: MyRankClient, author_id: int, name: str) -> None:
        super().__init__(timeout=180)
        self._api = api
        self._author_id = author_id
        self._name = name
        self.add_item(TemplatesSelect((), self._on_pick))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def _on_pick(self, interaction: discord.Interaction, templates: list[str]) -> None:
        await interaction.response.defer()
        try:
            table = await self._api.create_category(interaction.user.id, self._name, templates)
        except Exception as exc:
            await interaction.edit_original_response(content=None, embed=to_embed(exc), view=None)
            return
        await interaction.edit_original_response(
            content=None, embed=embeds.table_created(table), view=None
        )
        self.stop()


# ------------------------------------------------------------------ painel

class TablePanel(discord.ui.View):
    message: discord.Message | None = None

    def __init__(
        self, api: MyRankClient, author_id: int, table: Category, work_count: int,
    ) -> None:
        super().__init__(timeout=600)
        self.api = api
        self.author_id = author_id
        self.table = table
        self.work_count = work_count
        if CUSTOM_TEMPLATE not in table.templates:
            self.remove_item(self.custom_fields)
        if not table.subcategories:
            self.remove_item(self.edit_subcategory)

    def embed(self) -> discord.Embed:
        return embeds.table_detail(self.table, self.work_count)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self.author_id)

    async def on_timeout(self) -> None:
        await _disable_on_timeout(self, self.message)

    async def reload(self, discord_id: int) -> None:
        """Busca a tabela de novo e troca o painel por um novo, com os botoes certos."""
        if self.message is None:
            return
        try:
            categories = await self.api.get_categories(discord_id)
            table = next((c for c in categories if c.id == self.table.id), None)
            if table is None:
                self.stop()
                await self.message.edit(content="Essa tabela nao existe mais.", embed=None,
                                        view=None)
                return
            works = await self.api.list_works(discord_id, table.id)
        except Exception:
            return  # o painel antigo continua valendo; a mudanca ja foi avisada
        self.table = table
        self.work_count = len(works)
        panel = TablePanel(self.api, self.author_id, table, len(works))
        panel.message = self.message
        self.stop()
        try:
            await self.message.edit(embed=panel.embed(), view=panel)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Renomear", style=discord.ButtonStyle.primary, row=0)
    async def rename(
        self, interaction: discord.Interaction, button: discord.ui.Button[TablePanel]
    ) -> None:
        async def action(inner: discord.Interaction, name: str) -> None:
            await _run(inner, lambda: self.api.update_category(
                inner.user.id, self.table.id, name=name), f"Tabela renomeada para **{name}**.",
                self)

        await interaction.response.send_modal(
            NameModal("Renomear tabela", "Nome", action, default=self.table.name)
        )

    @discord.ui.button(label="Tipos", style=discord.ButtonStyle.primary, row=0)
    async def types(
        self, interaction: discord.Interaction, button: discord.ui.Button[TablePanel]
    ) -> None:
        async def on_pick(inner: discord.Interaction, templates: list[str]) -> None:
            await _run(inner, lambda: self.api.update_category(
                inner.user.id, self.table.id, templates=templates), "Tipos atualizados.", self)

        view = discord.ui.View(timeout=120)
        view.add_item(TemplatesSelect(self.table.templates, on_pick))
        await interaction.response.send_message(
            "Tirar um tipo so funciona se nenhuma obra da tabela for daquele tipo.",
            view=view, ephemeral=True,
        )

    @discord.ui.button(label="Campos proprios", style=discord.ButtonStyle.primary, row=0)
    async def custom_fields(
        self, interaction: discord.Interaction, button: discord.ui.Button[TablePanel]
    ) -> None:
        await interaction.response.send_message(
            embed=embeds.custom_fields(self.table), view=CustomFieldsView(self), ephemeral=True,
        )

    @discord.ui.button(label="Nova subcategoria", style=discord.ButtonStyle.secondary, row=1)
    async def new_subcategory(
        self, interaction: discord.Interaction, button: discord.ui.Button[TablePanel]
    ) -> None:
        async def action(inner: discord.Interaction, name: str) -> None:
            await _run(inner, lambda: self.api.create_subcategory(
                inner.user.id, self.table.id, name), f"Subcategoria **{name}** criada.", self)

        await interaction.response.send_modal(NameModal("Nova subcategoria", "Nome", action))

    @discord.ui.button(label="Editar subcategoria", style=discord.ButtonStyle.secondary, row=1)
    async def edit_subcategory(
        self, interaction: discord.Interaction, button: discord.ui.Button[TablePanel]
    ) -> None:
        options = [
            discord.SelectOption(label=_truncate(sub.name, 100), value=str(sub.id))
            for sub in self.table.subcategories[:25]
        ]
        view = discord.ui.View(timeout=120)
        view.add_item(ChoiceSelect(options, "Qual subcategoria?", self._subcategory_picked))
        await interaction.response.send_message(view=view, ephemeral=True)

    async def _subcategory_picked(self, interaction: discord.Interaction, value: str) -> None:
        sub = next(s for s in self.table.subcategories if str(s.id) == value)
        await interaction.response.edit_message(
            content=f"Subcategoria **{sub.name}**:", view=SubcategoryActions(self, sub.id, sub.name)
        )

    @discord.ui.button(label="Excluir tabela", style=discord.ButtonStyle.danger, row=2)
    async def delete(
        self, interaction: discord.Interaction, button: discord.ui.Button[TablePanel]
    ) -> None:
        async def confirmed(inner: discord.Interaction) -> None:
            await inner.response.defer()
            try:
                await self.api.delete_category(inner.user.id, self.table.id)
            except Exception as exc:
                await inner.edit_original_response(content=None, embed=to_embed(exc), view=None)
                return
            self.stop()
            await inner.edit_original_response(
                content=f"Tabela **{self.table.name}** excluida.", embed=None, view=None
            )

        confirm = ConfirmView(self.author_id, confirmed)
        await interaction.response.edit_message(
            content=embeds.delete_table_warning(self.table, self.work_count), embed=None,
            view=confirm,
        )
        confirm.message = await interaction.original_response()
        self.stop()


class SubcategoryActions(discord.ui.View):
    def __init__(self, panel: TablePanel, subcategory_id: int, name: str) -> None:
        super().__init__(timeout=120)
        self._panel = panel
        self._id = subcategory_id
        self._name = name

    @discord.ui.button(label="Renomear", style=discord.ButtonStyle.primary)
    async def rename(
        self, interaction: discord.Interaction, button: discord.ui.Button[SubcategoryActions]
    ) -> None:
        panel = self._panel

        async def action(inner: discord.Interaction, name: str) -> None:
            await _run(inner, lambda: panel.api.rename_subcategory(
                inner.user.id, panel.table.id, self._id, name), f"Renomeada para **{name}**.",
                panel)

        await interaction.response.send_modal(
            NameModal("Renomear subcategoria", "Nome", action, default=self._name)
        )

    @discord.ui.button(label="Apagar", style=discord.ButtonStyle.danger)
    async def delete(
        self, interaction: discord.Interaction, button: discord.ui.Button[SubcategoryActions]
    ) -> None:
        panel = self._panel

        async def confirmed(inner: discord.Interaction) -> None:
            await _run(inner, lambda: panel.api.delete_subcategory(
                inner.user.id, panel.table.id, self._id), f"Subcategoria **{self._name}** apagada.",
                panel)

        await interaction.response.edit_message(
            content=f"Apagar **{self._name}**? As obras dela continuam na tabela, so ficam "
                    "sem subcategoria.",
            view=ConfirmView(panel.author_id, confirmed),
        )


# ------------------------------------------------------------------ campos proprios

def fields_body(fields: tuple[CustomField, ...]) -> list[dict[str, str]]:
    """A lista completa que o PUT /custom-fields espera (com os ids de quem ja existe)."""
    return [{"id": f.id, "name": f.name, "type": f.type} for f in fields]


class CustomFieldsView(discord.ui.View):
    def __init__(self, panel: TablePanel) -> None:
        super().__init__(timeout=180)
        self._panel = panel
        fields = panel.table.custom_fields
        if len(fields) >= MAX_CUSTOM_FIELDS:
            self.remove_item(self.new_field)
        if fields:
            options = [
                discord.SelectOption(
                    label=_truncate(f.name, 100), value=f.id,
                    description=FIELD_TYPE_LABELS.get(f.type, f.type),
                )
                for f in fields
            ]
            self.add_item(ChoiceSelect(options, "Editar um campo...", self._field_picked))

    @discord.ui.button(label="Novo campo", style=discord.ButtonStyle.success)
    async def new_field(
        self, interaction: discord.Interaction, button: discord.ui.Button[CustomFieldsView]
    ) -> None:
        options = [discord.SelectOption(label=label, value=key) for key, label in FIELD_TYPES]
        view = discord.ui.View(timeout=120)
        view.add_item(ChoiceSelect(options, "Tipo do campo...", self._type_picked))
        await interaction.response.edit_message(
            content="O tipo nao muda depois: para trocar, e preciso apagar o campo e criar outro.",
            embed=None, view=view,
        )

    async def _type_picked(self, interaction: discord.Interaction, field_type: str) -> None:
        panel = self._panel

        async def action(inner: discord.Interaction, name: str) -> None:
            body = [*fields_body(panel.table.custom_fields), {"name": name, "type": field_type}]
            await _run(inner, lambda: panel.api.set_custom_fields(
                inner.user.id, panel.table.id, body), f"Campo **{name}** criado.", panel)

        await interaction.response.send_modal(
            NameModal("Novo campo", "Nome do campo", action, max_length=40)
        )

    async def _field_picked(self, interaction: discord.Interaction, field_id: str) -> None:
        field = next(f for f in self._panel.table.custom_fields if f.id == field_id)
        await interaction.response.edit_message(
            content=f"Campo **{field.name}** ({FIELD_TYPE_LABELS.get(field.type, field.type)}):",
            embed=None, view=CustomFieldActions(self._panel, field),
        )


class CustomFieldActions(discord.ui.View):
    def __init__(self, panel: TablePanel, field: CustomField) -> None:
        super().__init__(timeout=120)
        self._panel = panel
        self._field = field

    @discord.ui.button(label="Renomear", style=discord.ButtonStyle.primary)
    async def rename(
        self, interaction: discord.Interaction, button: discord.ui.Button[CustomFieldActions]
    ) -> None:
        panel, field = self._panel, self._field

        async def action(inner: discord.Interaction, name: str) -> None:
            body = [
                {"id": f.id, "name": name if f.id == field.id else f.name, "type": f.type}
                for f in panel.table.custom_fields
            ]
            await _run(inner, lambda: panel.api.set_custom_fields(
                inner.user.id, panel.table.id, body), f"Campo renomeado para **{name}**.", panel)

        await interaction.response.send_modal(
            NameModal("Renomear campo", "Nome do campo", action, default=field.name, max_length=40)
        )

    @discord.ui.button(label="Apagar", style=discord.ButtonStyle.danger)
    async def delete(
        self, interaction: discord.Interaction, button: discord.ui.Button[CustomFieldActions]
    ) -> None:
        panel, field = self._panel, self._field

        async def confirmed(inner: discord.Interaction) -> None:
            body = fields_body(tuple(f for f in panel.table.custom_fields if f.id != field.id))
            await _run(inner, lambda: panel.api.set_custom_fields(
                inner.user.id, panel.table.id, body), f"Campo **{field.name}** apagado.", panel)

        await interaction.response.edit_message(
            content=f"Apagar o campo **{field.name}**? O valor dele some de todas as obras da "
                    "tabela. Nao da para desfazer.",
            view=ConfirmView(panel.author_id, confirmed),
        )
