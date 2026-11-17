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
| `/perfil [pessoa]` | Seu resumo (obras, média, conquistas, seguidores), ou o perfil de outra pessoa, com o botão de seguir. |
| `/social feed [so_quem_sigo]` | O feed, com páginas; abra um take para reagir, comentar, editar ou apagar. |
| `/social pessoas <lista>` | Seguindo, seguidores, sugestões ou debatedores, com gosto parecido e obras em comum. |
| `/social buscar <nome>` | Procura pessoas no MyRank. |
| `/social pedidos` | Aprova ou recusa pedidos para seguir o seu perfil privado. |
| `/take <obra> <texto>` | Escreve um take (de 3 a 280 caracteres) sobre uma obra sua. |
| `/ranking [categoria]` | Suas obras na ordem do ranking, com páginas. |
| `/conquistas` | Conquistas desbloqueadas e o progresso das que faltam. |
| `/add <mídia> <busca>` | Busca a obra (com capa), confirma os dados, escolhe a tabela e a subcategoria e pede a nota. |
| `/add-manual <tabela> [tipo]` | Cadastra uma obra digitando os dados, para o que não existe em nenhuma busca. |
| `/manage <obra>` | Painel da obra: nota, dados (título, criador, lançamento, tempo, capa), tipo, subcategoria, campos próprios, "Atualizar dados" e remover. |
| `/tabela listar` | Suas tabelas, com tipos e subcategorias. |
| `/tabela criar <nome>` | Cria uma tabela e pergunta os tipos de obra que ela aceita. |
| `/tabela editar <tabela>` | Painel da tabela: renomear, tipos, subcategorias, campos próprios e excluir. |

O `/add` cobre as 8 mídias do site (filme, série, anime, mangá, jogo, livro, música e
álbum) e grava a obra como o site grava: com o tipo e a ficha da busca. As tabelas
oferecidas são as que aceitam aquele tipo. O que ainda falta do site está no roadmap.

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

Os comandos sociais (`/social`, `/take` e `/perfil <pessoa>`) precisam também de
`/api/social` na lista de rotas do bot, que está na branch `bot-social` do backend.
Sem ela, esses comandos respondem que o MyRank não respondeu e o log mostra um 403.

## License

© 2026 Guilherme Gocks. All rights reserved.
This source code is shared for portfolio purposes only and may not be copied, modified or redistributed without permission.
