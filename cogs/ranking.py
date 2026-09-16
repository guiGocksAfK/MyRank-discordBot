"""/ranking -- lista as obras do usuario na ordem que a API devolveu, paginada."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ui.errors import guarded
from ui.views import RankingView

log = logging.getLogger(__name__)


class RankingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="ranking", description="Mostra seu ranking de obras avaliadas."
    )
    @app_commands.describe(categoria="Filtra por uma categoria sua.")
    @guarded()
    async def ranking(self, interaction: discord.Interaction, categoria: int | None = None) -> None:
        works = await self.bot.api.list_works(interaction.user.id, categoria)  # type: ignore[attr-defined]

        category_name = None
        if categoria is not None:
            categories = await self.bot.api.get_categories(interaction.user.id)  # type: ignore[attr-defined]
            category_name = next((c.name for c in categories if c.id == categoria), None)

        view = RankingView(works, interaction.user.id, category_name)
        view.message = await interaction.followup.send(embed=view.embed(), view=view, wait=True)

    @ranking.autocomplete("categoria")
    async def ranking_categoria_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        try:
            categories = await self.bot.api.get_categories(interaction.user.id)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Falha ao buscar categorias para autocomplete de /ranking")
            return []

        current_norm = current.casefold()
        return [
            app_commands.Choice(name=category.name, value=category.id)
            for category in categories
            if current_norm in category.name.casefold()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RankingCog(bot))
