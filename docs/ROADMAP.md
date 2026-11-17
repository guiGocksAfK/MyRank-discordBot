# Roadmap

Meta: **tudo o que dá para fazer no site, dá para fazer pelo Discord.** As exceções
são poucas e estão explicadas em [decisoes.md](decisoes.md).

A ordem das fases é a ordem combinada. Quando algo ficar pronto, sai daqui (o
histórico fica no git). Cada fase diz o que o backend precisa liberar, porque a chave
do bot só vale nas rotas da lista `BOT_ROUTES` (ver "Rotas" em decisoes.md).

## Estado atual

Pronto e no `main`: `/perfil`, `/ranking`, `/conquistas`, `/add` (filme, série, jogo,
anime e livro) e `/manage` (editar nota, remover). Ainda não está no ar: falta subir
na VM e pôr a chave do bot no backend de lá.

## Fase 1 — Obras e tabelas completas

Tudo aqui usa rotas que o bot já pode chamar (`/api/works`, `/api/categories`,
`/api/external`). O backend não muda.

- **`/add` com as 8 mídias do site:** entram mangá, música e álbum.
- **`/add` salva a obra igual ao site:** guarda o template e a ficha (gêneros,
  episódios etc.) e deixa escolher a subcategoria. Hoje a obra do bot entra só com
  título, nota, capa, autor e data.
- **Obra sem busca:** cadastrar à mão, para o que não existe em nenhuma API.
- **`/buscar <mídia> <termo>`:** ver a obra (capa, ficha, sinopse) sem cadastrar,
  com um botão "Adicionar" que continua no fluxo do `/add`.
- **`/manage` edita tudo o que o site edita:** título, data, tempo, criador,
  subcategoria e campos próprios da tabela, além de "Atualizar dados".
- **`/tabela`:** criar, renomear e excluir tabelas; criar, renomear e excluir
  subcategorias; editar os campos próprios.

## Fase 2 — Social

Backend: liberar `/api/social`.

- **Ver o perfil de outra pessoa:** `/perfil @alguém` ou por nome. Perfil privado de
  quem você não segue aparece trancado, igual no site (quem decide é o backend).
- **Buscar pessoas, seguir e deixar de seguir.** Seguidores, seguindo e sugestões.
- **Pedidos para seguir:** listar, aprovar e recusar.
- **Feed:** ver o feed com páginas e reagir aos eventos.
- **Takes:** escrever, editar e apagar; ler e escrever comentários (com resposta),
  editar e apagar os seus.
- **Debatedores e gosto parecido:** as listas que o site mostra na aba social.

## Fase 3 — Notificações e IA

Backend: liberar `/api/notifications` e `/api/insights`.

- **`/notificacoes`:** ver, com páginas, e marcar todas como lidas.
- **`/insights`:** gerar a análise e conversar com ela. O limite de mensagens por
  dia é o mesmo do site, contado pelo backend.

## Fase 4 — Conta e organização

Backend: liberar `GET` e `PUT /api/users/me` e `/api/master-table-groups`.

- **`/config`:** idioma, perfil público ou privado e o resto das configurações que
  o site deixa mudar.
- **Ranking geral (tabela mestre):** criar e editar os agrupamentos e a ordem manual.
- **Criadores:** ver a tela de criadores. A conferir no site o que dela já vem da API
  e o que é montado no front.

## A decidir

- **Chat.** O Discord já é um chat; trazer as conversas do MyRank para dentro dele
  pede outro desenho (mensagem em tempo real chega pelo WebSocket, não pela API
  comum). Proposta: deixar para o fim e decidir se vale.

## Depois de cada fase

- Testar no servidor de testes do Discord contra o backend de produção.
- Subir na VM (`git pull` + `systemctl restart myrank-bot`).
