"""Componentes interativos: paginacao por botoes e os selects do /add.

`PaginatedView` nasceu generica ja no segundo consumidor (`/ranking` e `/conquistas`
precisavam do mesmo botao anterior/proximo, so o conteudo da pagina muda) -- e o
ponto em que valia extrair; antes disso, com um unico uso, seria enfeite. `ChoiceSelect`
segue a mesma regra: o /add tem dois selects (tabela, depois subcategoria) que so
diferem nas opcoes e no callback, entao o componente generico nasce direto.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import discord

from myrank.api import MyRankClient
from myrank.media import (
    CUSTOM_TEMPLATE,
    MediaType,
    by_template,
    tables_for,
    template_label,
)
from myrank.models import Badge, Category, ExternalDetails, ExternalResult, Work
from myrank.rankings import CreatorRank
from myrank.works import change_template_payload, refresh_payload
from ui import embeds
from ui.errors import to_embed
from ui.modals import (
    CustomFieldsModal,
    EditScoreModal,
    EditWorkModal,
    ManualWorkModal,
    ScoreModal,
)

PAGE_SIZE = 10


async def _check_author(interaction: discord.Interaction, author_id: int) -> bool:
    if interaction.user.id != author_id:
        await interaction.response.send_message(
            "Isso nao e seu -- rode o comando de novo.", ephemeral=True
        )
        return False
    return True


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _disable_on_timeout(
    view: discord.ui.View, message: discord.Message | None, **edit_kwargs: Any
) -> None:
    """Desabilita botoes e selects no timeout, ignorando mensagem apagada/expirada."""
    for child in view.children:
        if isinstance(child, (discord.ui.Button, discord.ui.Select)):
            child.disabled = True
    if message is not None:
        try:
            await message.edit(view=view, **edit_kwargs)
        except discord.HTTPException:
            pass


class PaginatedView(discord.ui.View):
    """Indice de pagina, travar pra quem chamou o comando, desabilitar no timeout.

    Subclasse guarda a lista de itens e implementa `embed()`; o `page_slice` recorta
    a pagina atual dessa lista.
    """

    message: discord.Message | None = None

    def __init__(self, total_items: int, author_id: int, page_size: int = PAGE_SIZE) -> None:
        super().__init__(timeout=180)
        self._total_items = total_items
        self._author_id = author_id
        self._page_size = page_size
        self._page = 0
        self._update_buttons()

    @property
    def total_pages(self) -> int:
        return max(1, -(-self._total_items // self._page_size))

    @property
    def current_page(self) -> int:
        return self._page + 1

    @property
    def page_start(self) -> int:
        return self._page * self._page_size

    @property
    def page_slice(self) -> slice:
        return slice(self.page_start, self.page_start + self._page_size)

    def embed(self) -> discord.Embed:
        raise NotImplementedError

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def on_timeout(self) -> None:
        await _disable_on_timeout(self, self.message)

    def _update_buttons(self) -> None:
        self.previous_page.disabled = self._page == 0
        self.next_page.disabled = self._page >= self.total_pages - 1

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[PaginatedView]
    ) -> None:
        self._page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[PaginatedView]
    ) -> None:
        self._page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class RankingView(PaginatedView):
    """O bot nao reordena `works` -- a posicao no ranking e responsabilidade da API."""

    def __init__(
        self, works: list[Work], author_id: int, category_name: str | None,
        sort: str | None = None,
    ) -> None:
        super().__init__(len(works), author_id)
        self._works = works
        self._category_name = category_name
        self._sort = sort

    def embed(self) -> discord.Embed:
        return embeds.ranking(
            self._works[self.page_slice],
            self.page_start,
            self.current_page,
            self.total_pages,
            self._category_name,
            self._sort,
        )


class CreatorsView(PaginatedView):
    """Ranking de criadores, ja ordenado pelo backend."""

    def __init__(
        self, creators: list[CreatorRank], author_id: int, order: str, creator_type: str | None,
    ) -> None:
        super().__init__(len(creators), author_id)
        self._creators = creators
        self._order = order
        self._type = creator_type

    def embed(self) -> discord.Embed:
        return embeds.creators(
            self._creators[self.page_slice], self.page_start, self.current_page,
            self.total_pages, self._order, self._type,
        )


class BadgesView(PaginatedView):
    def __init__(self, badges: list[Badge], author_id: int) -> None:
        super().__init__(len(badges), author_id)
        self._badges = badges

    def embed(self) -> discord.Embed:
        return embeds.badges(self._badges[self.page_slice], self.current_page, self.total_pages)


class ChoiceSelect(discord.ui.Select[discord.ui.View]):
    """Select generico: opcoes prontas, callback injetado. Usado na escolha de
    tabela e de subcategoria do /add."""

    def __init__(
        self,
        options: list[discord.SelectOption],
        placeholder: str,
        on_pick: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(placeholder=placeholder, options=options)
        self._on_pick = on_pick

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._on_pick(interaction, self.values[0])


class MediaResultView(PaginatedView):
    """Uma capa por pagina, na ordem retornada pelo backend."""

    def __init__(
        self,
        api: MyRankClient,
        author_id: int,
        media_type: MediaType,
        results: list[ExternalResult],
    ) -> None:
        super().__init__(len(results), author_id, page_size=1)
        self._api = api
        self._media_type = media_type
        self._results = results

    def embed(self) -> discord.Embed:
        return embeds.search_result(
            self._results[self._page], self._media_type.label,
            self.current_page, self.total_pages,
        )

    @discord.ui.button(label="Ver detalhes", style=discord.ButtonStyle.primary)
    async def show_details(
        self, interaction: discord.Interaction, button: discord.ui.Button[MediaResultView]
    ) -> None:
        # A abertura do modal fica para um novo clique, depois da consulta HTTP.
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = self._results[self._page]
        try:
            details = await self._api.external_details(
                interaction.user.id, self._media_type.endpoint, result.external_id
            )
            categories = await self._api.get_categories(interaction.user.id)
        except Exception as exc:
            await interaction.edit_original_response(embed=to_embed(exc), view=None)
            return
        view = MediaPreviewView(
            self._api, self._author_id, self._media_type, details,
            tables_for(self._media_type, categories),
        )
        await interaction.edit_original_response(
            embed=embeds.external_preview(details, self._media_type), view=view
        )


class MediaPreviewView(discord.ui.View):
    """Confirma a obra antes de escolher onde ela entra; nenhuma rede neste clique.

    `tables` ja vem filtrada: so as tabelas que aceitam esse tipo de midia.
    """

    def __init__(
        self, api: MyRankClient, author_id: int, media_type: MediaType,
        details: ExternalDetails, tables: list[Category],
    ) -> None:
        super().__init__(timeout=180)
        self._api = api
        self._author_id = author_id
        self._media_type = media_type
        self._details = details
        self._tables = tables

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    @discord.ui.button(label="E esta! Dar nota", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[MediaPreviewView]
    ) -> None:
        flow = _AddFlow(self._api, self._author_id, self._media_type, self._details)
        if not self._tables:
            await interaction.response.edit_message(
                embed=embeds.error(
                    f"Voce nao tem nenhuma tabela de {self._media_type.label}. "
                    f"Crie uma no site ({embeds.SITE_URL}) e rode o /add de novo."
                ),
                view=None,
            )
        elif len(self._tables) == 1:
            await flow.table_chosen(interaction, self._tables[0])
        else:
            await interaction.response.edit_message(
                embed=embeds.pick_table(self._details),
                view=TablePickView(flow, self._tables),
            )

    @discord.ui.button(label="Nao e esta", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button[MediaPreviewView]
    ) -> None:
        await interaction.response.edit_message(
            content="Use as setas na mensagem da busca para conferir outro resultado.",
            embed=None, view=None,
        )
        self.stop()


class _Flow:
    """Passos finais de um cadastro: escolher onde a obra entra e abrir o modal.

    `_AddFlow` (obra da busca) e `ManualFlow` (obra digitada) so diferem no modal
    que abrem no fim; as telas de tabela e subcategoria servem as duas.
    """

    api: MyRankClient
    author_id: int
    title: str
    image_url: str | None = None

    async def table_chosen(self, interaction: discord.Interaction, table: Category) -> None:
        if table.subcategories:
            await interaction.response.edit_message(
                embed=embeds.pick_subcategory(self.title, self.image_url, table),
                view=SubcategoryPickView(self, table),
            )
        else:
            await self.ask_score(interaction, table, None)

    async def ask_score(
        self, interaction: discord.Interaction, table: Category, subcategory_id: int | None
    ) -> None:
        raise NotImplementedError


class _AddFlow(_Flow):
    """O que falta decidir no /add depois de confirmar a obra: tabela, subcategoria
    e nota. Cada passo so aparece quando ha escolha de verdade a fazer."""

    def __init__(
        self, api: MyRankClient, author_id: int, media_type: MediaType,
        details: ExternalDetails,
    ) -> None:
        self.api = api
        self.author_id = author_id
        self.media_type = media_type
        self.details = details
        self.title = details.title
        self.image_url = details.image_url

    async def ask_score(
        self, interaction: discord.Interaction, table: Category, subcategory_id: int | None
    ) -> None:
        await interaction.response.send_modal(
            ScoreModal(self.api, self.media_type, self.details, table.id, subcategory_id)
        )


class ManualFlow(_Flow):
    """/add-manual: a tabela ja veio no comando; falta o tipo (se a tabela for mista),
    a subcategoria (se houver) e os dados."""

    def __init__(
        self, api: MyRankClient, author_id: int, table: Category, template: str | None,
    ) -> None:
        self.api = api
        self.author_id = author_id
        self.table = table
        self.template = template
        self.title = table.name

    def first_step(self) -> tuple[discord.Embed, discord.ui.View]:
        """Primeira mensagem do /add-manual. Ela sempre tem um componente: o modal so
        pode abrir como resposta a um clique, e o comando ja respondeu com o defer."""
        if self.template is None:
            return embeds.pick_template(self.table), TemplatePickView(self)
        if self.table.subcategories:
            return (
                embeds.pick_subcategory(self.title, None, self.table),
                SubcategoryPickView(self, self.table),
            )
        return embeds.manual_ready(self.table, self.template), OpenModalView(self)

    async def template_chosen(self, interaction: discord.Interaction, template: str) -> None:
        self.template = template
        await self.table_chosen(interaction, self.table)

    async def ask_score(
        self, interaction: discord.Interaction, table: Category, subcategory_id: int | None
    ) -> None:
        assert self.template is not None
        await interaction.response.send_modal(
            ManualWorkModal(self.api, self.template, table.id, subcategory_id)
        )


class TemplatePickView(discord.ui.View):
    """Tabela mista (ex.: Series + Animes): a obra digitada precisa de um tipo."""

    def __init__(self, flow: ManualFlow) -> None:
        super().__init__(timeout=120)
        self._flow = flow
        options = [
            discord.SelectOption(label=template_label(t), value=t)
            for t in flow.table.templates[:25]
        ]
        self.add_item(ChoiceSelect(options, "Que tipo de obra e?", self._on_pick))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._flow.author_id)

    async def _on_pick(self, interaction: discord.Interaction, value: str) -> None:
        await self._flow.template_chosen(interaction, value)


class OpenModalView(discord.ui.View):
    """Um botao so, para abrir o modal quando nao ha mais nada a escolher antes."""

    def __init__(self, flow: ManualFlow) -> None:
        super().__init__(timeout=300)
        self._flow = flow

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._flow.author_id)

    @discord.ui.button(label="Preencher dados", style=discord.ButtonStyle.success)
    async def open_modal(
        self, interaction: discord.Interaction, button: discord.ui.Button[OpenModalView]
    ) -> None:
        await self._flow.ask_score(interaction, self._flow.table, None)


class TablePickView(discord.ui.View):
    """So aparece quando a pessoa tem mais de uma tabela que aceita o tipo."""

    def __init__(self, flow: _Flow, tables: list[Category]) -> None:
        super().__init__(timeout=120)
        self._flow = flow
        self._tables = {str(table.id): table for table in tables[:25]}
        options = [
            discord.SelectOption(label=_truncate(table.name, 100), value=key)
            for key, table in self._tables.items()
        ]
        self.add_item(ChoiceSelect(options, "Escolha a tabela...", self._on_pick))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._flow.author_id)

    async def _on_pick(self, interaction: discord.Interaction, value: str) -> None:
        await self._flow.table_chosen(interaction, self._tables[value])


NO_SUBCATEGORY = "0"


class SubcategoryPickView(discord.ui.View):
    """Subcategoria e opcional, como no site: a primeira opcao e deixar sem."""

    def __init__(self, flow: _Flow, table: Category) -> None:
        super().__init__(timeout=120)
        self._flow = flow
        self._table = table
        options = [discord.SelectOption(label="Sem subcategoria", value=NO_SUBCATEGORY)]
        options += [
            discord.SelectOption(label=_truncate(sub.name, 100), value=str(sub.id))
            for sub in table.subcategories[:24]
        ]
        self.add_item(ChoiceSelect(options, "Escolha a subcategoria...", self._on_pick))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._flow.author_id)

    async def _on_pick(self, interaction: discord.Interaction, value: str) -> None:
        subcategory_id = None if value == NO_SUBCATEGORY else int(value)
        await self._flow.ask_score(interaction, self._table, subcategory_id)


class ConfirmView(discord.ui.View):
    """Confirmar/cancelar generico com timeout. Primeiro uso e o /remover dentro do
    /manage, mas nao ha nada de remocao aqui dentro -- quem decide o que "confirmar"
    faz e o callback injetado."""

    message: discord.Message | None = None

    def __init__(
        self,
        author_id: int,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
        *,
        timeout: float = 30,
        on_cancel: Callable[[discord.Interaction], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self._author_id = author_id
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def on_timeout(self) -> None:
        await _disable_on_timeout(
            self, self.message, content="Tempo esgotado -- nada foi alterado."
        )

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[ConfirmView]
    ) -> None:
        await self._on_confirm(interaction)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button[ConfirmView]
    ) -> None:
        if self._on_cancel is not None:
            await self._on_cancel(interaction)
            return
        await interaction.response.edit_message(content="Cancelado.", embed=None, view=None)


class ManageView(discord.ui.View):
    """Painel do /manage: tudo o que o site deixa mudar numa obra.

    Os botoes dependem da obra: "Subcategoria" so com subcategorias na tabela,
    "Campos proprios" so em obra Personalizado com campos, "Atualizar dados" so em
    obra de um tipo que tem busca. Depois de cada edicao o painel se atualiza com a
    obra que o backend devolveu, para a proxima edicao partir do valor certo.
    """

    message: discord.Message | None = None

    def __init__(
        self, api: MyRankClient, author_id: int, work: Work, table: Category | None = None,
    ) -> None:
        super().__init__(timeout=600)
        self._api = api
        self._author_id = author_id
        self._work = work
        self._table = table
        if table is None or not table.subcategories:
            self.remove_item(self.move_subcategory)
        if work.template != CUSTOM_TEMPLATE or table is None or not table.custom_fields:
            self.remove_item(self.edit_custom_fields)
        if work.template is None or work.template == CUSTOM_TEMPLATE:
            self.remove_item(self.refresh)
        if table is None or len(table.templates) < 2:
            self.remove_item(self.change_type)

    @property
    def work(self) -> Work:
        return self._work

    @property
    def api(self) -> MyRankClient:
        return self._api

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def on_timeout(self) -> None:
        await _disable_on_timeout(self, self.message)

    async def saved(self, work: Work) -> None:
        """Chamado pelos modais e selects depois que o backend gravou.

        O painel e refeito, e nao so redesenhado: os botoes dependem da obra (trocar
        o tipo muda se existe "Atualizar dados" e "Campos proprios").
        """
        self._work = work
        if self.message is None:
            return
        panel = ManageView(self._api, self._author_id, work, self._table)
        panel.message = self.message
        self.stop()
        try:
            await self.message.edit(embed=embeds.work_detail(work, self._table), view=panel)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Editar nota", style=discord.ButtonStyle.primary, row=0)
    async def edit_score(
        self, interaction: discord.Interaction, button: discord.ui.Button[ManageView]
    ) -> None:
        await interaction.response.send_modal(
            EditScoreModal(self._api, self._work, on_saved=self.saved)
        )

    @discord.ui.button(label="Editar dados", style=discord.ButtonStyle.primary, row=0)
    async def edit_data(
        self, interaction: discord.Interaction, button: discord.ui.Button[ManageView]
    ) -> None:
        await interaction.response.send_modal(
            EditWorkModal(self._api, self._work, on_saved=self.saved)
        )

    @discord.ui.button(label="Campos proprios", style=discord.ButtonStyle.primary, row=0)
    async def edit_custom_fields(
        self, interaction: discord.Interaction, button: discord.ui.Button[ManageView]
    ) -> None:
        assert self._table is not None
        await interaction.response.send_modal(CustomFieldsModal(
            self._api, self._work, self._table.custom_fields, on_saved=self.saved
        ))

    @discord.ui.button(label="Trocar tipo", style=discord.ButtonStyle.secondary, row=1)
    async def change_type(
        self, interaction: discord.Interaction, button: discord.ui.Button[ManageView]
    ) -> None:
        assert self._table is not None
        options = [
            discord.SelectOption(label=template_label(t), value=t)
            for t in self._table.templates if t != self._work.template
        ]
        view = discord.ui.View(timeout=120)
        view.add_item(ChoiceSelect(options, "Novo tipo...", self._type_picked))
        await interaction.response.send_message(
            f"De que tipo e **{self._work.title}**? A ligacao com a busca e os campos "
            "proprios saem, porque eram do tipo antigo.",
            view=view, ephemeral=True,
        )

    async def _type_picked(self, interaction: discord.Interaction, template: str) -> None:
        await interaction.response.defer()
        try:
            work = await self._api.update_work(
                interaction.user.id, self._work.id, change_template_payload(self._work, template)
            )
        except Exception as exc:
            await interaction.edit_original_response(content=None, embed=to_embed(exc), view=None)
            return
        await interaction.edit_original_response(
            content=None, embed=embeds.work_updated(work), view=None
        )
        await self.saved(work)

    @discord.ui.button(label="Subcategoria", style=discord.ButtonStyle.secondary, row=1)
    async def move_subcategory(
        self, interaction: discord.Interaction, button: discord.ui.Button[ManageView]
    ) -> None:
        assert self._table is not None
        await interaction.response.send_message(
            f"Em que subcategoria **{self._work.title}** fica?",
            view=SubcategoryMoveView(self, self._table), ephemeral=True,
        )

    @discord.ui.button(label="Atualizar dados", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(
        self, interaction: discord.Interaction, button: discord.ui.Button[ManageView]
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        assert self._work.template is not None
        media = by_template(self._work.template)
        external_id = self._work.details.get("externalId")
        if external_id:
            await self.apply_refresh(interaction, media, str(external_id))
            return
        # Obra antiga, sem id da busca: a pessoa confirma qual e, como no site,
        # para nao ligar a obra a um remake com o mesmo nome.
        try:
            results = await self._api.external_search(
                interaction.user.id, media.endpoint, self._work.title
            )
        except Exception as exc:
            await interaction.edit_original_response(embed=to_embed(exc))
            return
        if not results:
            await interaction.edit_original_response(embed=embeds.error(
                "Nao achei essa obra na busca. Confira o titulo em Editar dados."
            ))
            return
        await interaction.edit_original_response(
            content="Qual destes e a sua obra?", view=RefreshPickView(self, media, results),
        )

    async def apply_refresh(
        self, interaction: discord.Interaction, media: MediaType, external_id: str
    ) -> None:
        """Busca a ficha de novo e grava. A interacao ja foi confirmada (defer)."""
        try:
            fetched = await self._api.external_details(
                interaction.user.id, media.endpoint, external_id
            )
            work = await self._api.update_work(
                interaction.user.id, self._work.id, refresh_payload(self._work, media, fetched)
            )
        except Exception as exc:
            await interaction.edit_original_response(content=None, embed=to_embed(exc), view=None)
            return
        await interaction.edit_original_response(
            content=None, embed=embeds.work_refreshed(work), view=None
        )
        await self.saved(work)

    @discord.ui.button(label="Remover", style=discord.ButtonStyle.danger, row=1)
    async def remove(
        self, interaction: discord.Interaction, button: discord.ui.Button[ManageView]
    ) -> None:
        confirm_view = ConfirmView(self._author_id, self._confirm_remove)
        await interaction.response.edit_message(
            content=f"Tem certeza que quer remover **{self._work.title}**?",
            embed=None,
            view=confirm_view,
        )
        confirm_view.message = await interaction.original_response()
        self.stop()

    async def _confirm_remove(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            await self._api.delete_work(interaction.user.id, self._work.id)
        except Exception as exc:
            await interaction.edit_original_response(content=None, embed=to_embed(exc), view=None)
            return
        await interaction.edit_original_response(
            content=None, embed=embeds.work_removed(self._work.title), view=None
        )


class SubcategoryMoveView(discord.ui.View):
    """Troca a subcategoria de uma obra que ja existe. "Sem subcategoria" manda 0,
    que e como o backend entende "tirar da subcategoria"."""

    def __init__(self, panel: ManageView, table: Category) -> None:
        super().__init__(timeout=120)
        self._panel = panel
        options = [discord.SelectOption(
            label="Sem subcategoria", value=NO_SUBCATEGORY,
            default=panel.work.subcategory_id is None,
        )]
        options += [
            discord.SelectOption(
                label=_truncate(sub.name, 100), value=str(sub.id),
                default=sub.id == panel.work.subcategory_id,
            )
            for sub in table.subcategories[:24]
        ]
        self.add_item(ChoiceSelect(options, "Escolha a subcategoria...", self._on_pick))

    async def _on_pick(self, interaction: discord.Interaction, value: str) -> None:
        await interaction.response.defer()
        try:
            work = await self._panel.api.update_work(
                interaction.user.id, self._panel.work.id, {"subcategoryId": int(value)}
            )
        except Exception as exc:
            await interaction.edit_original_response(content=None, embed=to_embed(exc), view=None)
            return
        await interaction.edit_original_response(
            content=None, embed=embeds.work_updated(work), view=None
        )
        await self._panel.saved(work)


class RefreshPickView(discord.ui.View):
    """Atualizar dados de obra sem id da busca: a pessoa escolhe o resultado certo."""

    def __init__(
        self, panel: ManageView, media: MediaType, results: list[ExternalResult],
    ) -> None:
        super().__init__(timeout=120)
        self._panel = panel
        self._media = media
        options = [
            discord.SelectOption(
                label=_truncate(result.title or "Sem titulo", 100),
                description=_truncate(
                    " | ".join(x for x in (result.year, result.creator) if x) or "-", 100
                ),
                value=result.external_id,
            )
            for result in results[:25]
        ]
        self.add_item(ChoiceSelect(options, "Escolha a obra certa...", self._on_pick))

    async def _on_pick(self, interaction: discord.Interaction, value: str) -> None:
        await interaction.response.defer()
        await self._panel.apply_refresh(interaction, self._media, value)
