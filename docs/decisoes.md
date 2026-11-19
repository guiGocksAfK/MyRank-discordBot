# Decisões

O que já foi decidido e por quê. O que falta fazer fica em [ROADMAP.md](ROADMAP.md).

## Escopo

- **O bot faz tudo o que o site faz** (decidido em 2026-11-17). O site continua sendo
  o lugar "completo", mas ninguém deveria precisar sair do Discord para usar o MyRank
  no dia a dia.
- **Ficam só no site, de propósito:**
  - **Cadastro, login, senha e códigos por email.** No bot a pessoa já é ela mesma pelo
    Discord; esses fluxos não têm sentido aqui.
  - **Tutorial de conta nova.** Para usar o bot a pessoa entra no site com o Discord
    uma vez, e o tutorial aparece ali.
  - **Excluir a conta e sair dos outros aparelhos.** São irreversíveis ou derrubam
    sessões. A chave do bot age como qualquer usuário, então ela nunca deve conseguir
    fazer isso: se a chave vazar, o estrago fica limitado ao que dá para desfazer.
- **O bot não calcula nada.** Nota final, posição, progresso de conquista, perfil
  trancado: tudo vem pronto do backend. Se faltar algo, cria-se o endpoint no Java.

## Rotas

- **A chave do bot é uma chave mestra:** quem tem ela age como qualquer pessoa
  vinculada. Por isso ela só vale numa lista fechada de rotas (`BOT_ROUTES` no
  `BotAuthenticationFilter` do backend).
- **A lista cresce por fase, nunca "libera tudo".** Cada fase do roadmap diz o que
  abre. Rota nova entra na lista junto com o comando que usa ela.
- **Nunca entram:** `/api/auth`, `DELETE /api/users/me`,
  `POST /api/users/me/deletion-code` e `POST /api/users/me/sessions/revoke`. Como
  `/api/users` mistura rotas permitidas e proibidas, a liberação dela tem que ser por
  rota e método, não pelo prefixo.

## Obras

- **A tabela é escolhida pelo tipo, não pelo nome.** Cada tabela tem os tipos que
  aceita (`templates`); o `/add` só oferece essas. Com uma só, ela é usada direto; com
  várias, a pessoa escolhe; com nenhuma, o bot manda criar no site. O bot nunca cria
  tabela sozinho.
- **A obra é gravada como o site grava:** com o tipo e a ficha da busca, mais
  `provider` e `externalId`, que o "Atualizar dados" usa depois.
- **Subcategoria é opcional**, e a pergunta só aparece se a tabela tiver alguma.
- **Tempo só é perguntado quando falta:** se a busca não trouxe e o tipo usa a nota
  ponderada pelo tempo, o modal da nota pede as horas (opcional).
- **Sem `/buscar` separado** (estava no plano e saiu em 2026-11-17). O `/add` já
  deixa ver capa e ficha sem cadastrar nada, e no site a busca também só existe dentro
  do "adicionar". Seriam dois comandos fazendo a mesma coisa.
- **Obra sem busca é o `/add-manual`**, com a tabela no próprio comando. O modal do
  Discord aceita só 5 campos: título, nota, criador, lançamento e horas (só nos tipos
  com nota ponderada pelo tempo). Capa e campos próprios ficam para a edição no
  `/manage`. Tabela mista pergunta o tipo antes.
- **Lançamento aceita ano ou data** (`2008` ou `20/01/2008`); só o ano vira 1º de
  janeiro, como o backend já faz com o Google Books.
- **O `/manage` é um painel com botões**, e só mostra o que faz sentido para a obra:
  "Subcategoria" se a tabela tiver alguma, "Campos próprios" em obra Personalizado com
  campos, "Atualizar dados" em obra de um tipo com busca. Depois de cada edição o
  painel é redesenhado com a obra que o backend devolveu.
- **"Atualizar dados" faz o mesmo que o botão do site:** busca a ficha de novo pelo
  `externalId` e só troca o que muda com o tempo; capa e data só entram se estiverem
  vazias. Obra antiga, sem `externalId`, mostra os resultados da busca pelo título
  para a pessoa escolher, para não ligar a obra a um remake.
- **Apagar no "Editar dados":** criador e capa vazios apagam, como no site. A data
  vazia mantém a que está, porque o backend não tem como apagar a data numa edição.
- **Editar manda só o que mudou.** O `PUT` do backend é parcial; mandar a obra inteira
  arriscaria apagar a ficha ou a subcategoria.

## Tabelas

- **`/tabela` com três subcomandos** (`listar`, `criar`, `editar`); o resto é painel
  com botões, como o `/manage`. Os botões dependem da tabela: "Campos próprios" só com
  Personalizado, "Editar subcategoria" só se houver alguma.
- **Excluir tabela diz quantas obras vão junto.** O banco apaga as obras (e os takes
  delas) com a tabela; o aviso dá o número antes da confirmação.
- **Apagar subcategoria não apaga obra:** elas ficam na tabela, sem subcategoria, e o
  aviso diz isso.
- **Campos próprios:** o tipo é escolhido na criação e não muda (regra do backend);
  apagar um campo apaga o valor dele em todas as obras, com confirmação.
- **Trocar o tipo de uma obra** só aparece em tabela mista. Como no site, a ligação com
  a busca antiga e os campos próprios saem, porque eram do tipo anterior.
- **Depois de cada mudança o painel é refeito com o que o backend devolveu**, e não só
  redesenhado: os botões que fazem sentido podem ter mudado.

## Social

- **`/api/social` inteiro entrou na lista do bot** (2026-11-17). Nada ali apaga conta
  ou derruba sessão; quem vê o quê (perfil trancado, take de perfil privado) continua
  decidido pelo backend.
- **Perfil de outra pessoa pelo nome do MyRank**, com autocompletar pela busca de
  pessoas. Pela menção do Discord ficou para decidir (ver ROADMAP).
- **O botão de seguir diz o que o clique faz**: Seguir, Pedir para seguir (privado),
  Cancelar pedido ou Deixar de seguir. Depois do clique o perfil é buscado de novo.
- **Feed pedido ao backend página por página** (8 takes por página, mais os cards de
  "avaliou N obras"); página vazia é o fim. O bot não junta nem reordena nada.
- **Take abre numa mensagem só para a pessoa**, com reações (a dela fica destacada;
  clicar de novo tira), comentários e, se o take for dela, editar e apagar.
- **Comentários em dois níveis, como no site**; comentar, responder, editar e apagar
  acontecem na própria mensagem, que é redesenhada com a lista nova.
- **`/take` recebe o texto no próprio comando**, sem janela: o comando já confirma a
  interação para buscar dados, e depois disso o Discord não deixa abrir janela.
- **Pedidos para seguir respondem só para a pessoa** (mensagem privada), porque dizem
  quem quer seguir quem.

## Notificações, IA e conta

- **Notificações, IA e configurações respondem só para a pessoa** (mensagem privada):
  dizem quem fez o quê, falam do gosto dela ou mostram dados da conta.
- **`/insights gerar` usa todas as obras ou uma tabela**, com o mínimo de 5 obras do
  site. Tirar obras uma a uma, como no painel do site, ficou de fora: no Discord
  seria uma lista de seleção longa para pouco ganho.
- **"Gerar de novo" só aparece quando o bot sabe que obras entraram** (análise vinda
  do `/insights gerar`). A análise mais recente (`/insights ver`) não diz isso.
- **A IA tem 75 segundos de espera**, como no site; o resto da API, 10.
- **Sem mensagens de IA no dia, "Perguntar" e "Gerar de novo" ficam desligados.** O
  backend conta e recusa de qualquer forma; o botão desligado só evita o clique à toa.
- **`/config` salva cada mudança na hora**, como a página do site. Bio e foto vazias
  apagam. Senha, sair dos aparelhos e excluir a conta continuam só no site.
- **O `/perfil` próprio usa `/users/me` para achar o id** e mostra o mesmo perfil que
  os outros veem. Se o backend ainda não liberou `/users/me`, cai no resumo antigo
  (obras, média e conquistas), em vez de falhar.

## Rankings

- **Ranking geral e de criadores calculados no backend** (`/api/rankings`), e não no
  bot: no site eles eram montados no front, e copiar a conta para cá quebraria a
  regra de que o bot não calcula nada. O backend ganhou as duas rotas, com a regra
  do front; o front ainda calcula do jeito dele (trocar está no ROADMAP do backend).
- **`/ranking` sem ordem usa a configuração "nota ponderada" da conta**, como o site.
  Com tabela, desempata pela posição dela; sem tabela, pela ordem manual do
  "Unificado". A posição mostrada é a da lista, não o campo `position`.
- **Se o backend ainda não tem `/api/rankings`, o `/ranking` cai na lista simples**
  (todas as obras pela nota final), em vez de falhar.
- **Filtros da barra do site** (ano, horas, gênero, status...) ficaram de fora do bot.

## Comportamento

- **Toda resposta vem do backend na ordem dele.** O bot não reordena ranking, feed nem
  resultado de busca.
- **O que apaga pede confirmação** (botão "Confirmar"), como no `/manage` hoje.
- **Só quem chamou o comando mexe nos botões dele.** As páginas e os selects travam
  para os outros e se desligam sozinhos depois de um tempo.
