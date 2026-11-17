"""Componentes interativos: paginacao por botoes e os selects do /add.

`PaginatedView` nasceu generica ja no segundo consumidor (`/ranking` e `/conquistas`
precisavam do mesmo botao anterior/proximo, so o conteudo da pagina muda) -- e o
ponto em que valia extrair; antes disso, com um unico uso, seria enfeite. `ChoiceSelect`
segue a mesma regra: o /add tem dois selects (resultado externo, depois categoria)
que so diferem nas opcoes e no callback, entao o componente generico nasce direto.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

from myrank.api import MyRankClient
from myrank.media import MediaType, match_category
from myrank.models import Badge, Category, ExternalDetails, ExternalResult, Work
from ui import embeds
from ui.errors import to_embed
from ui.modals import EditScoreModal, ScoreModal

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
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)

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

    def __init__(self, works: list[Work], author_id: int, category_name: str | None) -> None:
        super().__init__(len(works), author_id)
        self._works = works
        self._category_name = category_name

    def embed(self) -> discord.Embed:
        return embeds.ranking(
            self._works[self.page_slice],
            self.page_start,
            self.current_page,
            self.total_pages,
            self._category_name,
        )


class BadgesView(PaginatedView):
    def __init__(self, badges: list[Badge], author_id: int) -> None:
        super().__init__(len(badges), author_id)
        self._badges = badges

    def embed(self) -> discord.Embed:
        return embeds.badges(self._badges[self.page_slice], self.current_page, self.total_pages)


class ChoiceSelect(discord.ui.Select[discord.ui.View]):
    """Select generico: opcoes prontas, callback injetado. Usado pelo resultado da
    busca externa e pela escolha de categoria do /add -- so isso, nao ganha um uso
    a mais que justifique mais generalidade que essa."""

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
            self._api, self._author_id, self._media_type, details, categories
        )
        await interaction.edit_original_response(
            embed=embeds.external_preview(details, self._media_type.label), view=view
        )


class MediaPreviewView(discord.ui.View):
    """Confirma a obra antes de abrir o modal; nenhuma rede neste clique."""

    def __init__(
        self, api: MyRankClient, author_id: int, media_type: MediaType,
        details: ExternalDetails, categories: list[Category],
    ) -> None:
        super().__init__(timeout=180)
        self._api = api
        self._author_id = author_id
        self._media_type = media_type
        self._details = details
        self._categories = categories

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    @discord.ui.button(label="E esta! Dar nota", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[MediaPreviewView]
    ) -> None:
        category = match_category(self._media_type, self._categories)
        if category is not None:
            await interaction.response.send_modal(
                ScoreModal(self._api, self._details, category.id)
            )
        elif self._categories:
            await interaction.response.edit_message(
                embed=embeds.pick_category(self._details),
                view=CategoryPickView(
                    self._api, self._author_id, self._details, self._categories
                ),
            )
        else:
            await interaction.response.edit_message(
                embed=embeds.error("Crie uma categoria no MyRank antes de cadastrar a obra."),
                view=None,
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


class CategoryPickView(discord.ui.View):
    """Passo 2 do /add, so aparece quando `match_category` nao acha um match
    confiavel -- o bot nunca escolhe nem cria categoria sozinho."""

    def __init__(
        self,
        api: MyRankClient,
        author_id: int,
        details: ExternalDetails,
        categories: list[Category],
    ) -> None:
        super().__init__(timeout=120)
        self._api = api
        self._author_id = author_id
        self._details = details
        options = [
            discord.SelectOption(label=_truncate(category.name, 100), value=str(category.id))
            for category in categories[:25]
        ]
        self.add_item(ChoiceSelect(options, "Escolha a categoria...", self._on_pick))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def _on_pick(self, interaction: discord.Interaction, category_id: str) -> None:
        await interaction.response.send_modal(
            ScoreModal(self._api, self._details, int(category_id))
        )


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
    ) -> None:
        super().__init__(timeout=timeout)
        self._author_id = author_id
        self._on_confirm = on_confirm

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message is not None:
            await self.message.edit(content="Tempo esgotado -- nada foi alterado.", view=self)

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[ConfirmView]
    ) -> None:
        await self._on_confirm(interaction)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button[ConfirmView]
    ) -> None:
        await interaction.response.edit_message(content="Cancelado.", embed=None, view=None)


class ManageView(discord.ui.View):
    """Editar a nota ou remover uma obra especifica -- alvo do /manage."""

    def __init__(self, api: MyRankClient, author_id: int, work: Work) -> None:
        super().__init__(timeout=120)
        self._api = api
        self._author_id = author_id
        self._work = work

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    @discord.ui.button(label="Editar nota", style=discord.ButtonStyle.primary)
    async def edit_score(
        self, interaction: discord.Interaction, button: discord.ui.Button[ManageView]
    ) -> None:
        await interaction.response.send_modal(EditScoreModal(self._api, self._work))

    @discord.ui.button(label="Remover", style=discord.ButtonStyle.danger)
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
