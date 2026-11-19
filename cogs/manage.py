"""/manage -- tudo o que o site deixa mudar numa obra: nota, dados, subcategoria,
campos proprios, "Atualizar dados" e remover."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ui import embeds
from ui.errors import guarded
from ui.views import ManageView

log = logging.getLogger(__name__)


class ManageCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="manage", description="Edita ou remove uma obra sua."
    )
    @app_commands.describe(obra="Titulo da obra (autocompletar).")
    @guarded()
    async def manage(self, interaction: discord.Interaction, obra: int) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        works = await api.list_works(interaction.user.id)
        work = next((w for w in works if w.id == obra), None)
        if work is None:
            await interaction.followup.send(
                embed=embeds.error("Essa obra nao existe mais -- rode `/manage` de novo.")
            )
            return

        # A tabela diz que botoes fazem sentido (subcategorias, campos proprios).
        categories = await api.get_categories(interaction.user.id)
        table = next((c for c in categories if c.id == work.category_id), None)
        view = ManageView(api, interaction.user.id, work, table)
        view.message = await interaction.followup.send(
            embed=embeds.work_detail(work, table), view=view, wait=True
        )

    @manage.autocomplete("obra")
    async def manage_obra_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        try:
            works = await self.bot.api.list_works(interaction.user.id)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Falha ao buscar obras para autocomplete de /manage")
            return []

        current_norm = current.casefold()
        return [
            app_commands.Choice(name=work.title[:100], value=work.id)
            for work in works
            if current_norm in work.title.casefold()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ManageCog(bot))
