# MyRank-discordBot

Front-end alternativo do [MyRank](https://myrank.duckdns.org) dentro do Discord. A meta
é fazer pelo Discord tudo o que dá para fazer pelo site (o plano está em
[docs/ROADMAP.md](docs/ROADMAP.md), e as decisões em [docs/decisoes.md](docs/decisoes.md)).

O bot é **apenas um cliente HTTP** da API do MyRank: não tem banco, não fala com
TMDB/RAWG/Jikan/Google Books direto e **não calcula nada** — nem nota ponderada, nem
progresso de conquista, nem ranking. Toda regra de negócio mora no backend Java.

> Se um comando precisaria de uma lógica que a API não expõe, a resposta certa é criar
> o endpoint no Java — não implementar a lógica aqui.

## Comandos

| Comando | O que faz |
|---|---|
| `/perfil` | Seu resumo: quantas obras, média das notas e conquistas. |
| `/ranking [categoria]` | Suas obras na ordem do ranking, com páginas. |
| `/conquistas` | Conquistas desbloqueadas e o progresso das que faltam. |
| `/add <mídia> <busca>` | Busca a obra (com capa), confirma os dados, escolhe a tabela e pede a nota. |
| `/manage <obra>` | Edita a nota ou remove uma obra sua (com confirmação). |

Hoje o `/add` cobre filme, série, jogo, anime e livro. O que ainda falta do site está
no roadmap.

## Arquitetura

```
bot.py                 entrypoint: Settings -> MyRankClient -> cogs -> sync
myrank/                ZERO imports de discord.py aqui dentro
  config.py            Settings frozen, validado no boot, segredos mascarados no repr
  models.py            dataclasses frozen; finalScore é read-only
  errors.py            NotLinkedError, RateLimitedError, ApiError, ApiUnavailableError
  api.py               MyRankClient: um AsyncClient, headers, status -> exceção
  media.py             choice -> endpoint externo -> palpite de categoria
ui/                    único lugar que importa discord.py
  embeds.py            tema #d4af37
  errors.py            exceção -> embed + decorator @guarded (defer + captura)
  views.py             paginação por botões, resultados com capa, selects, confirmação
  modals.py            modais de nota (criar e editar)
cogs/                  um cog por comando
tests/                 client testado com httpx.MockTransport, views sem gateway
docs/                  roadmap e decisões
```

### Regras que sustentam a estrutura

1. **`myrank/` não importa `discord`.** O client recebe `discord_id: int`, nunca uma
   `Interaction`. É o que permite testar a camada HTTP inteira sem gateway nem token.
2. **`discord_id` é parâmetro obrigatório de todo método do client** — não há como
   esquecer o header por omissão. O valor vem sempre de `interaction.user.id`, jamais
   de argumento digitado.
3. **Erro é traduzido duas vezes, em dois lugares fixos:** status → exceção em
   `api.py`, exceção → embed em `ui/errors.py`. Cogs não têm `try/except`.
4. **`@guarded` em todo comando** faz `defer` + captura. Nenhuma exceção escapa sem
   virar mensagem — silêncio é o pior modo de falha num bot.
5. **Modelos `frozen`, sem setter e sem método de cálculo.** É onde "o bot não calcula
   nada" vira estrutura em vez de promessa.
6. **Segredo nunca em log.** `Settings.__repr__` mascara token e API key; 5xx do
   backend vira mensagem genérica com detalhe só no journald.

## Autenticação

Sem login de usuário e sem JWT. Chave de serviço fixa + Discord ID resolvido pelo
backend:

```
X-Bot-Key:    <MYRANK_BOT_API_KEY>
X-Discord-Id: <interaction.user.id>
```

**Vincular a conta:** entrar uma vez no site com "Entrar com Discord". Se o email do
Discord for o mesmo de uma conta que já existe, o login cai nessa conta e grava o
Discord nela. Não existe comando de vinculação.

**401:** quando a mensagem do backend fala em vínculo, o bot avisa a pessoa para entrar
no site com o Discord. Qualquer outro 401 (chave errada, header faltando) é problema
de configuração: a pessoa vê uma mensagem genérica e o detalhe vai para o log.

**Rotas liberadas:** a chave do bot só vale para as rotas da lista `BOT_ROUTES` do
`BotAuthenticationFilter` no backend. Fora dela o backend responde 403, e o bot
registra no log como erro de configuração. Cada fase do roadmap diz quais rotas abre.

## Rodando localmente

Python 3.11 ou mais novo. No 3.13+ o `requirements.txt` instala o `audioop-lts`,
porque o discord.py importa um módulo que saiu da biblioteca padrão (o bot não usa voz).

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # preencha DISCORD_TOKEN e MYRANK_BOT_API_KEY
python bot.py
```

Defina `DISCORD_GUILD_ID` em dev: a sincronização por guild é instantânea, a global
leva até uma hora. `MYRANK_BOT_API_KEY` precisa ser o mesmo valor configurado no
backend.

```bash
pytest          # testes (sem rede, sem Discord)
ruff check .
mypy .
```

## Deploy

Mesma VM da Oracle Always Free onde roda o backend. `systemd` com `Restart=always` e
`EnvironmentFile` apontando para o `.env` (permissão `600`), usuário dedicado, log via
journald. O bot não expõe porta e não entra no Caddy. Em produção,
`MYRANK_API_URL=https://myrank.duckdns.org/api`.

```bash
sudo cp myrank-bot.service /etc/systemd/system/
sudo systemctl enable --now myrank-bot
journalctl -u myrank-bot -f
```

O backend da VM também precisa da mesma `MYRANK_BOT_API_KEY` no `.env` dele. Sem ela,
o filtro do bot fica desligado e todo pedido do bot volta 401.

## Dependência do backend

O suporte ao bot já está no `master` do
[MyRank-backend](https://github.com/guiGocksAfK/MyRank-backend): coluna
`users.discord_id`, `BotAuthenticationFilter` (chave + lista de rotas) e rate limit
por usuário do Discord no `RateLimitFilter`.

## License

© 2026 Guilherme Gocks. All rights reserved.
This source code is shared for portfolio purposes only and may not be copied, modified or redistributed without permission.
