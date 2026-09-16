"""Paginacao por botoes.

`PaginatedView` nasceu generica ja no segundo consumidor (`/ranking` e `/conquistas`
precisavam do mesmo botao anterior/proximo, so o conteudo da pagina muda) -- e o
ponto em que valia extrair; antes disso, com um unico uso, seria enfeite.
"""

from __future__ import annotations

import discord

from myrank.models import Badge, Work
from ui import embeds

PAGE_SIZE = 10


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
        if interaction.user.id != self._author_id:
            await interaction.response.send_message(
                "Isso nao e seu -- rode o comando de novo.", ephemeral=True
            )
            return False
        return True

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
