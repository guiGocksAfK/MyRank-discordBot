"""/social (feed, pessoas, busca, pedidos para seguir) e /take."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ui import embeds
from ui import social_embeds as se
from ui.errors import guarded
from ui.social import FEED_PAGE_SIZE, FeedView, PeopleView

log = logging.getLogger(__name__)

# (valor da API, titulo, texto quando a lista vem vazia)
LISTS = {
    "seguindo": ("following", "Quem voce segue", "Voce ainda nao segue ninguem."),
    "seguidores": ("followers", "Seus seguidores", "Ninguem te segue ainda."),
    "sugestoes": ("suggestions", "Sugestoes para seguir", "Sem sugestoes agora."),
    "debatedores": ("debaters", "Quem mais discorda de voce",
                    "Ainda nao ha obras em comum suficientes para comparar."),
}


class SocialCog(commands.GroupCog, group_name="social", group_description="Feed e pessoas."):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="feed", description="Takes e avaliacoes de quem voce segue e dos perfis publicos."
    )
    @app_commands.describe(so_quem_sigo="Mostrar so quem voce segue (e voce).")
    @guarded()
    async def feed(self, interaction: discord.Interaction, so_quem_sigo: bool = False) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        items = await api.feed(interaction.user.id, 0, FEED_PAGE_SIZE,
                               following_only=so_quem_sigo)
        view = FeedView(api, interaction.user.id, items, following_only=so_quem_sigo)
        view.message = await interaction.followup.send(embed=view.embed(), view=view, wait=True)

    @app_commands.command(  # type: ignore[arg-type]
        name="pessoas", description="Quem voce segue, seus seguidores, sugestoes ou debatedores."
    )
    @app_commands.describe(lista="Qual lista.")
    @app_commands.choices(lista=[
        app_commands.Choice(name="Seguindo", value="seguindo"),
        app_commands.Choice(name="Seguidores", value="seguidores"),
        app_commands.Choice(name="Sugestoes", value="sugestoes"),
        app_commands.Choice(name="Debatedores", value="debatedores"),
    ])
    @guarded()
    async def pessoas(self, interaction: discord.Interaction, lista: str) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        kind, title, empty = LISTS[lista]
        users = await api.people(interaction.user.id, kind)
        view = PeopleView(api, interaction.user.id, title, users, empty=empty)
        view.message = await interaction.followup.send(embed=view.embed(), view=view, wait=True)

    @app_commands.command(  # type: ignore[arg-type]
        name="buscar", description="Procura pessoas no MyRank pelo nome."
    )
    @app_commands.describe(nome="Nome ou parte do nome.")
    @guarded()
    async def buscar(self, interaction: discord.Interaction, nome: str) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        users = await api.search_users(interaction.user.id, nome.strip())
        view = PeopleView(api, interaction.user.id, f"Pessoas: {nome.strip()}"[:256], users,
                          empty="Ninguem com esse nome.")
        view.message = await interaction.followup.send(embed=view.embed(), view=view, wait=True)

    @app_commands.command(  # type: ignore[arg-type]
        name="pedidos", description="Pedidos para seguir o seu perfil privado."
    )
    @guarded(ephemeral=True)
    async def pedidos(self, interaction: discord.Interaction) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        users = await api.people(interaction.user.id, "follow-requests")
        view = PeopleView(api, interaction.user.id, "Pedidos para seguir", users,
                          empty="Nenhum pedido pendente.", requests=True)
        view.message = await interaction.followup.send(
            embed=view.embed(), view=view, wait=True, ephemeral=True
        )


class TakeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]
        name="take", description="Escreve um take (opiniao curta) sobre uma obra sua."
    )
    @app_commands.describe(obra="Uma obra sua (autocompletar).", texto="De 3 a 280 caracteres.")
    @guarded()
    async def take(self, interaction: discord.Interaction, obra: int, texto: str) -> None:
        texto = texto.strip()
        if not 3 <= len(texto) <= 280:
            await interaction.followup.send(
                embed=embeds.error("O take precisa ter de 3 a 280 caracteres.")
            )
            return
        item = await self.bot.api.post_take(interaction.user.id, obra, texto)  # type: ignore[attr-defined]
        await interaction.followup.send(embed=se.take_posted(item))

    @take.autocomplete("obra")
    async def take_obra_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        try:
            works = await self.bot.api.list_works(interaction.user.id)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Falha ao buscar obras para autocomplete de /take")
            return []
        current_norm = current.casefold()
        return [
            app_commands.Choice(name=work.title[:100], value=work.id)
            for work in works
            if current_norm in work.title.casefold()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SocialCog(bot))
    await bot.add_cog(TakeCog(bot))
