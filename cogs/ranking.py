"""/ranking e /criadores -- os rankings do site, ja ordenados pelo backend.

/ranking usa `/rankings/unified`: sem tabela, as tabelas do "Unificado" do site (com a
ordem manual nos empates); com tabela, so ela. /criadores usa `/rankings/creators`.
O bot nao reordena nem calcula nada.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from myrank.errors import ApiUnavailableError
from myrank.rankings import CREATOR_ORDERS, CREATOR_TYPES, UNIFIED_SORTS
from ui.errors import guarded
from ui.views import CreatorsView, RankingView

log = logging.getLogger(__name__)


class RankingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="ranking", description="Mostra seu ranking de obras, como no site."
    )
    @app_commands.describe(
        tabela="So uma tabela sua. Sem ela, o ranking geral.",
        ordem="Nota, nota ponderada ou tempo. Sem ela, vale a sua configuracao.",
    )
    @app_commands.choices(ordem=[
        app_commands.Choice(name=label, value=value) for value, label in UNIFIED_SORTS
    ])
    @guarded()
    async def ranking(
        self, interaction: discord.Interaction, tabela: int | None = None,
        ordem: str | None = None,
    ) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        try:
            works = await api.unified_ranking(interaction.user.id, ordem, tabela)
        except ApiUnavailableError:
            # Backend ainda sem /rankings liberado para o bot: a lista simples por nota.
            log.warning("/rankings/unified indisponivel; usando /works")
            works = await api.list_works(interaction.user.id, tabela)

        table_name = None
        if tabela is not None:
            tables = await api.get_categories(interaction.user.id)
            table_name = next((t.name for t in tables if t.id == tabela), None)

        view = RankingView(works, interaction.user.id, table_name, ordem)
        view.message = await interaction.followup.send(embed=view.embed(), view=view, wait=True)

    @ranking.autocomplete("tabela")
    async def ranking_tabela_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        try:
            tables = await self.bot.api.get_categories(interaction.user.id)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Falha ao buscar tabelas para autocomplete de /ranking")
            return []

        current_norm = current.casefold()
        return [
            app_commands.Choice(name=table.name[:100], value=table.id)
            for table in tables
            if current_norm in table.name.casefold()
        ][:25]

    @app_commands.command(  # type: ignore[arg-type]
        name="criadores", description="Ranking dos diretores, escritores e estudios das suas obras."
    )
    @app_commands.describe(ordem="Media, ponderada ou mais obras.", tipo="So um tipo de criador.")
    @app_commands.choices(
        ordem=[app_commands.Choice(name=label, value=value) for value, label in CREATOR_ORDERS],
        tipo=[app_commands.Choice(name=t, value=t) for t in CREATOR_TYPES],
    )
    @guarded()
    async def criadores(
        self, interaction: discord.Interaction, ordem: str = "avg", tipo: str | None = None,
    ) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        creators = await api.creator_ranking(interaction.user.id, ordem, tipo)
        view = CreatorsView(creators, interaction.user.id, ordem, tipo)
        view.message = await interaction.followup.send(embed=view.embed(), view=view, wait=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RankingCog(bot))
