"""/perfil -- primeiro comando, teste real da arquitetura em myrank/ e ui/.

`/api/users` esta fora do escopo da bot key (so /works, /categories, /badges,
/external aceitam a X-Bot-Key), entao nao ha `GET /users/me` pra chamar. O perfil sai
de duas chamadas que ja existem (obras + conquistas) e da identidade que o proprio
Discord ja tem -- nao precisa perguntar nome nem avatar pro MyRank.
"""

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
        api = self.bot.api  # type: ignore[attr-defined]
        works = await api.list_works(interaction.user.id)
        badges = await api.get_badges(interaction.user.id)

        average = sum(work.final_score for work in works) / len(works) if works else None
        embed = embeds.profile(
            interaction.user.display_name,
            interaction.user.display_avatar.url,
            len(works),
            average,
            sum(1 for badge in badges if badge.unlocked),
            len(badges),
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
