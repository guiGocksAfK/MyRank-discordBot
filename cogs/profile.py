"""/perfil -- primeiro comando, teste real da arquitetura em myrank/ e ui/."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ui import embeds
from ui.errors import guarded


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="perfil", description="Mostra seu perfil no MyRank."
    )
    @guarded()
    async def perfil(self, interaction: discord.Interaction) -> None:
        user = await self.bot.api.get_me(interaction.user.id)  # type: ignore[attr-defined]
        await interaction.followup.send(embed=embeds.profile(user))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
