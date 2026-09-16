"""/conquistas -- segundo consumidor de PaginatedView, ao lado do /ranking."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ui.errors import guarded
from ui.views import BadgesView


class BadgesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="conquistas", description="Mostra suas conquistas no MyRank."
    )
    @guarded()
    async def conquistas(self, interaction: discord.Interaction) -> None:
        badges = await self.bot.api.get_badges(interaction.user.id)  # type: ignore[attr-defined]
        view = BadgesView(badges, interaction.user.id)
        view.message = await interaction.followup.send(embed=view.embed(), view=view, wait=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BadgesCog(bot))
