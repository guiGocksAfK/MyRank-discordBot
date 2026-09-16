"""Paginacao por botoes.

Unico consumidor por enquanto e o /ranking. Vira componente reutilizavel quando um
segundo comando (ex. /conquistas) precisar do mesmo padrao -- generalizar antes disso
e enfeite sem caso de uso real.
"""

from __future__ import annotations

import discord

from myrank.models import Work
from ui import embeds

PAGE_SIZE = 10


class RankingView(discord.ui.View):
    """Uma pagina de cada vez sobre uma lista ja ordenada pelo backend.

    O bot nao reordena `works` -- a posicao no ranking e responsabilidade da API.
    """

    message: discord.Message | None = None

    def __init__(self, works: list[Work], author_id: int, category_name: str | None) -> None:
        super().__init__(timeout=180)
        self._works = works
        self._author_id = author_id
        self._category_name = category_name
        self._page = 0
        self._update_buttons()

    @property
    def total_pages(self) -> int:
        return max(1, -(-len(self._works) // PAGE_SIZE))

    def embed(self) -> discord.Embed:
        start = self._page * PAGE_SIZE
        page_works = self._works[start : start + PAGE_SIZE]
        return embeds.ranking(
            page_works, start, self._page + 1, self.total_pages, self._category_name
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._author_id:
            await interaction.response.send_message(
                "Esse ranking nao e seu -- rode `/ranking` de novo.", ephemeral=True
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
        self, interaction: discord.Interaction, button: discord.ui.Button[RankingView]
    ) -> None:
        self._page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[RankingView]
    ) -> None:
        self._page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)
