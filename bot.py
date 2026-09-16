"""Entrypoint do bot.

Responsabilidades: carregar Settings, criar e fechar o MyRankClient unico,
carregar os cogs e sincronizar os slash commands.
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from myrank.api import MyRankClient
from myrank.config import Settings

log = logging.getLogger("myrank.bot")

COGS: tuple[str, ...] = (
    "cogs.profile",
    "cogs.ranking",
    "cogs.add",
    "cogs.manage",
)


class MyRankBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        # Intents.none(): o bot e 100% slash command e nao le mensagem nenhuma.
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.none())
        self.settings = settings
        self.api = MyRankClient(settings)

    async def setup_hook(self) -> None:
        await self.api.start()

        for cog in COGS:
            try:
                await self.load_extension(cog)
            except commands.ExtensionNotFound:
                log.debug("Cog ainda nao implementado: %s", cog)

        if self.settings.guild_id is not None:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Comandos sincronizados na guild %s.", self.settings.guild_id)
        else:
            await self.tree.sync()
            log.info("Comandos sincronizados globalmente.")

    async def close(self) -> None:
        await self.api.aclose()
        await super().close()


async def main() -> None:
    settings = Settings.load()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    log.info("Iniciando com %r", settings)

    async with MyRankBot(settings) as bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
