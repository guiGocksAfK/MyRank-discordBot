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

## Comportamento

- **Toda resposta vem do backend na ordem dele.** O bot não reordena ranking, feed nem
  resultado de busca.
- **O que apaga pede confirmação** (botão "Confirmar"), como no `/manage` hoje.
- **Só quem chamou o comando mexe nos botões dele.** As páginas e os selects travam
  para os outros e se desligam sozinhos depois de um tempo.
