"""/config -- as configuracoes da conta, so para a pessoa."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ui.config import ConfigView, config_embed
from ui.errors import guarded


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="config", description="Suas configuracoes do MyRank (perfil, privacidade, avisos...)."
    )
    @guarded(ephemeral=True)
    async def config(self, interaction: discord.Interaction) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        account = await api.me(interaction.user.id)
        await interaction.followup.send(
            embed=config_embed(account), view=ConfigView(api, interaction.user.id, account),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigCog(bot))
