"""/add -- busca externa, casamento de categoria e nota.

Primeiro uso de verdade de `myrank/media.py`: o mapa de choice -> endpoint e o
palpite de categoria existiam desde o inicio, mas so aqui viram comando real.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from myrank.media import MEDIA_TYPES, by_key
from ui.errors import guarded
from ui.views import MediaResultView

MEDIA_CHOICES = [
    app_commands.Choice(name=media_type.label, value=media_type.key) for media_type in MEDIA_TYPES
]


class AddCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="add", description="Adiciona uma obra avaliada ao seu MyRank."
    )
    @app_commands.describe(midia="Tipo de midia.", busca="Titulo ou parte do titulo.")
    @app_commands.choices(midia=MEDIA_CHOICES)
    @guarded()
    async def add(self, interaction: discord.Interaction, midia: str, busca: str) -> None:
        media_type = by_key(midia)
        api = self.bot.api  # type: ignore[attr-defined]
        results = await api.external_search(interaction.user.id, media_type.endpoint, busca)

        if not results:
            await interaction.followup.send(
                f"Nenhum resultado para **{busca}**. Tente outro termo."
            )
            return

        view = MediaResultView(api, interaction.user.id, media_type, results)
        await interaction.followup.send(
            f"Encontrei {len(results)} resultado(s) para **{busca}**. Qual e o certo?",
            view=view,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AddCog(bot))
