# Roadmap

Meta: **tudo o que dá para fazer no site, dá para fazer pelo Discord.** As exceções
são poucas e estão explicadas em [decisoes.md](decisoes.md).

A ordem das fases é a ordem combinada. Quando algo ficar pronto, sai daqui (o
histórico fica no git). Cada fase diz o que o backend precisa liberar, porque a chave
do bot só vale nas rotas da lista `BOT_ROUTES` (ver "Rotas" em decisoes.md).

## Estado atual

**Fase 1 (obras e tabelas) pronta**, sem mudar nada no backend: `/perfil`, `/ranking`,
`/conquistas`, `/add` (as 8 mídias, com tipo, ficha e subcategoria, igual ao site),
`/add-manual` (obra digitada, inclusive Personalizado), `/manage` (nota, dados, capa,
tipo, subcategoria, campos próprios, "Atualizar dados" e remover) e `/tabela` (listar,
criar, renomear, tipos, subcategorias, campos próprios e excluir).

**Fase 2 (social) pronta no bot:** `/perfil <pessoa>` (com seguir, pedir para seguir
e obras), `/social feed` (takes e avaliações, reações e comentários), `/social pessoas`
(seguindo, seguidores, sugestões, debatedores), `/social buscar`, `/social pedidos` e
`/take`. Precisa do backend com `/api/social` na lista do bot (branch `bot-social` do
MyRank-backend).

**Fase 3 (notificações e IA) pronta no bot:** `/notificacoes` (páginas e "marcar
todas como lidas") e `/insights gerar | ver | perguntar` (análise, conversa e gerar de
novo, com o mesmo limite diário do site).

**Fase 4 (conta) pronta no bot:** `/config` (nome, bio, foto, privacidade, idioma,
mensagens, avisos silenciados, nota ponderada e visualização) e o `/perfil` próprio
agora é o perfil do MyRank (nome, bio, top, conquistas).

**Rankings:** `/ranking [tabela] [ordem]` agora é o ranking do site (o geral usa a
seleção e a ordem manual do "Unificado") e `/criadores` é o ranking de criadores. As
contas foram para o backend (`/api/rankings`), com a mesma regra do site.

As fases 2 a 4 e os rankings precisam do backend da branch `bot-social` (social,
notificações, IA, rankings e `GET`/`PUT /api/users/me` na lista do bot).

Ainda não está no ar: falta testar no Discord, subir o backend com a branch
`bot-social`, subir o bot na VM e pôr a chave do bot no backend de lá.

## A decidir

- **`/perfil @alguém` pela menção do Discord.** Hoje é pelo nome no MyRank. A menção
  precisa de uma rota nova no backend que diga qual conta do MyRank é de um Discord,
  e isso expõe a ligação entre as duas contas para quem usa o bot.
- **Chat.** O Discord já é um chat; trazer as conversas do MyRank para dentro dele
  pede outro desenho (mensagem em tempo real chega pelo WebSocket, não pela API
  comum). Proposta: deixar para o fim e decidir se vale.

## Depois de cada fase

- Testar no servidor de testes do Discord contra o backend de produção.
- Subir na VM (`git pull` + `systemctl restart myrank-bot`).
