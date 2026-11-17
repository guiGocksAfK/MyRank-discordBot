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
- **Editar manda só o que mudou.** O `PUT` do backend é parcial; mandar a obra inteira
  arriscaria apagar a ficha ou a subcategoria.

## Comportamento

- **Toda resposta vem do backend na ordem dele.** O bot não reordena ranking, feed nem
  resultado de busca.
- **O que apaga pede confirmação** (botão "Confirmar"), como no `/manage` hoje.
- **Só quem chamou o comando mexe nos botões dele.** As páginas e os selects travam
  para os outros e se desligam sozinhos depois de um tempo.
