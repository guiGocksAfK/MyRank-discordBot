"""/perfil -- o seu perfil do MyRank, ou o de outra pessoa.

Os dois vem prontos de `/social/users/{id}` (o seu, pelo id que `/users/me` da). O de
outra pessoa pode vir trancado, quando o perfil e privado e voce nao segue.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from myrank.errors import ApiUnavailableError
from ui import embeds
from ui import social_embeds as se
from ui.errors import guarded
from ui.social import ProfileView

log = logging.getLogger(__name__)


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="perfil", description="Mostra o seu perfil no MyRank, ou o de outra pessoa."
    )
    @app_commands.describe(pessoa="Outra pessoa do MyRank (autocompletar pelo nome).")
    @guarded()
    async def perfil(self, interaction: discord.Interaction, pessoa: int | None = None) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        if pessoa is not None:
            profile = await api.profile(interaction.user.id, pessoa)
            view = ProfileView(api, interaction.user.id, profile)
            view.message = await interaction.followup.send(
                embed=se.social_profile(profile), view=view, wait=True,
            )
            return

        try:
            account = await api.me(interaction.user.id)
            profile = await api.profile(interaction.user.id, account.id)
            summary = await api.social_summary(interaction.user.id)
        except ApiUnavailableError:
            # Backend ainda sem /users/me ou /social liberado: resumo pelas obras.
            log.warning("Perfil completo indisponivel no /perfil; usando o resumo simples")
            await interaction.followup.send(embed=await self._simple_profile(interaction))
            return
        embed = se.social_profile(profile)
        if summary.pending_follow_requests:
            embed.add_field(
                name="Pedidos para seguir",
                value=f"{summary.pending_follow_requests} -- veja em `/social pedidos`",
            )
        embed.set_footer(text="Mude nome, bio, foto e privacidade com /config.")
        await interaction.followup.send(embed=embed)

    async def _simple_profile(self, interaction: discord.Interaction) -> discord.Embed:
        api = self.bot.api  # type: ignore[attr-defined]
        works = await api.list_works(interaction.user.id)
        badges = await api.get_badges(interaction.user.id)
        average = sum(work.final_score for work in works) / len(works) if works else None
        return embeds.profile(
            interaction.user.display_name,
            interaction.user.display_avatar.url,
            len(works),
            average,
            sum(1 for badge in badges if badge.unlocked),
            len(badges),
        )

    @perfil.autocomplete("pessoa")
    async def perfil_pessoa_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        if len(current.strip()) < 2:
            return []
        try:
            users = await self.bot.api.search_users(interaction.user.id, current.strip())  # type: ignore[attr-defined]
        except Exception:
            log.exception("Falha ao buscar pessoas para autocomplete de /perfil")
            return []
        return [app_commands.Choice(name=u.username[:100], value=u.id) for u in users[:25]]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
