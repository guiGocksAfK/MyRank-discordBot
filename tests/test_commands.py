"""Todo comando carrega e vira um slash command valido, sem conectar no Discord.

Pega erro que so apareceria ao ligar o bot: anotacao de parametro que o discord.py
nao consegue ler, nome repetido, parametro sem descricao valida.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot import COGS

EXPECTED = {
    "perfil", "ranking", "conquistas", "add", "add-manual", "manage",
    "tabela listar", "tabela criar", "tabela editar", "take",
    "social feed", "social pessoas", "social buscar", "social pedidos",
    "notificacoes", "insights gerar", "insights ver", "insights perguntar", "config",
    "criadores",
}


async def test_every_command_loads_and_serializes() -> None:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    for cog in COGS:
        await bot.load_extension(cog)
    names = set()
    for command in bot.tree.walk_commands():
        if isinstance(command, discord.app_commands.Command):
            command.to_dict(bot.tree)  # o mesmo formato que vai para o Discord no sync
            names.add(command.qualified_name)
    assert names == EXPECTED
