# MyRank-discordBot

Front-end alternativo do [MyRank](https://myrank.duckdns.org) dentro do Discord.

O bot é **apenas um cliente HTTP** da API do MyRank: não tem banco, não fala com
TMDB/RAWG/Jikan/Google Books direto e **não calcula nada** — nem nota ponderada, nem
progresso de conquista, nem ranking. Toda regra de negócio mora no backend Java.

> Se um comando precisaria de uma lógica que a API não expõe, a resposta certa é criar
> o endpoint no Java — não implementar a lógica aqui.

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
cogs/                  um cog por comando
tests/                 client testado com httpx.MockTransport
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

Um 401 significa que a conta do Discord não está vinculada. O onboarding é entrar uma
vez no site com "Login com Discord" — não existe comando de vinculação.

## Rodando localmente

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # preencha DISCORD_TOKEN e MYRANK_BOT_API_KEY
python bot.py
```

Defina `DISCORD_GUILD_ID` em dev: a sincronização por guild é instantânea, a global
leva até uma hora.

```bash
pytest          # testes (sem rede, sem Discord)
ruff check .
mypy .
```

## Deploy

Mesma VM da Oracle Always Free onde roda o backend. `systemd` com `Restart=always` e
`EnvironmentFile` apontando para o `.env` (permissão `600`), usuário dedicado, log via
journald. O bot não expõe porta e não entra no Caddy.

```bash
sudo cp myrank-bot.service /etc/systemd/system/
sudo systemctl enable --now myrank-bot
journalctl -u myrank-bot -f
```

## Dependência do backend

Requer as alterações da branch `discord-bot` do
[MyRank-backend](https://github.com/guiGocksAfK/MyRank-backend): coluna `discord_id`
(migration V11), `BotAuthenticationFilter` e rate limit por usuário.
