# MyRank — Discord Bot

Rate and rank anything you love, without leaving Discord. MyRank is built around
pop culture (movies, series, anime, manga, games, books and music): scores become
tables, tables merge into a single ranking, and the ranking becomes a profile of
your taste.

The web app is live at **[myrank.duckdns.org](https://myrank.duckdns.org/)**. This
repository contains the Discord bot, a second client of the same API: the API lives
in [MyRank-backend](https://github.com/guiGocksAfK/MyRank-backend) and the web app
in [MyRank-frontend](https://github.com/guiGocksAfK/MyRank).

The goal is that **everything you can do on the site, you can do from Discord**.
The plan is in [`docs/ROADMAP.md`](docs/ROADMAP.md) and the decisions in
[`docs/decisoes.md`](docs/decisoes.md), both in Portuguese.

## Features

- **Works and tables.** `/add` searches all eight media types of the site (movie,
  series, anime, manga, game, book, song and album) with covers, then asks for the
  table, subcategory and score. `/add-manual` covers anything no search finds,
  including Custom tables. `/manage` edits a work's score, details, cover, type,
  subcategory and custom fields, refreshes its metadata or removes it. `/tabela`
  lists, creates, renames and deletes tables, with their types, subcategories and
  custom fields.
- **Rankings.** `/ranking` is the site's unified ranking (or a single table's), by
  score, time-weighted score or time; `/criadores` ranks the directors, writers and
  studios behind your works.
- **Social.** Profiles with follow and follow requests, the feed with reactions and
  threaded comments, people lists (following, followers, suggestions, debaters),
  user search and takes.
- **Notifications and AI Insights.** Paged notifications with "mark all as read",
  plus the AI taste analysis and its follow-up chat, sharing the site's daily
  budget.
- **Settings.** `/config` changes name, bio, photo, privacy, language, who can
  message you, muted notifications, time-weighted score and list/grid view.
- **Achievements.** Unlocked badges and the progress of the rest.

### Commands

| Command | What it does |
|---|---|
| `/perfil [pessoa]` | Your MyRank profile (name, bio, top works, achievements, followers), or someone else's, with a follow button. |
| `/ranking [tabela] [ordem]` | The unified ranking, or one table's, by score, time-weighted score or time. |
| `/criadores [ordem] [tipo]` | Ranking of the directors, writers and studios in your works. |
| `/conquistas` | Unlocked achievements and progress on the others. |
| `/add <midia> <busca>` | Searches a work, confirms its data, picks table and subcategory, and asks for the score. |
| `/add-manual <tabela> [tipo]` | Adds a work by typing its data, for what no search finds. |
| `/manage <obra>` | Work panel: score, details, type, subcategory, custom fields, refresh and remove. |
| `/tabela listar` | Your tables, with types and subcategories. |
| `/tabela criar <nome>` | Creates a table and asks which work types it accepts. |
| `/tabela editar <tabela>` | Table panel: rename, types, subcategories, custom fields and delete. |
| `/social feed [so_quem_sigo]` | The feed, paged; open a take to react, comment, edit or delete it. |
| `/social pessoas <lista>` | Following, followers, suggestions or debaters, with affinity and works in common. |
| `/social buscar <nome>` | Searches people on MyRank. |
| `/social pedidos` | Approves or rejects requests to follow your private profile. |
| `/take <obra> <texto>` | Writes a take (3 to 280 characters) about one of your works. |
| `/notificacoes` | Your notifications, paged, with "mark all as read". |
| `/insights gerar [tabela]` | AI analysis of your taste (all works or one table). |
| `/insights ver` | Opens the latest analysis. |
| `/insights perguntar <pergunta>` | Asks the AI about the analysis (uses one of the day's AI messages). |
| `/config` | Profile, privacy, language, messages, notifications, time-weighted score and view. |

Command and option names are in Portuguese, like the bot's replies.

**Kept on the site on purpose:** sign-up, login, passwords and e-mail codes (on
Discord you already are yourself), the new-account tutorial, and deleting the
account or signing out of other devices. The bot's key acts as any linked user, so
it must never reach anything irreversible.

## Architecture and hosting

| Component | Runs on | Notes |
|---|---|---|
| Bot | Oracle Cloud VM (ARM64), same as the API | `systemd` service with `Restart=always`, dedicated user, logs in journald. Opens no port and sits outside Caddy: it only connects out, to Discord and to the API. |
| API | Same VM, in Docker | See the [backend README](https://github.com/guiGocksAfK/MyRank-backend#architecture-and-hosting). |

The bot is **only an HTTP client** of the MyRank API. It has no database, never
calls TMDB, RAWG or any other source directly, and **computes nothing**: final
scores, positions, achievement progress and rankings all come ready from the API.
If a command would need logic the API does not expose, the answer is a new
endpoint in the backend, not code here.

A few design rules hold the structure together:

1. **`myrank/` never imports `discord`.** The HTTP client takes a plain
   `discord_id: int`, never an `Interaction`, so the whole HTTP layer is tested
   without a gateway or a token.
2. **`discord_id` is a required argument of every client method**, so the header
   cannot be forgotten. It always comes from `interaction.user.id`, never from
   something the user typed.
3. **Errors are translated twice, in two fixed places:** status to exception in
   `myrank/api.py`, exception to embed in `ui/errors.py`. Cogs have no `try/except`.
4. **`@guarded` on every command** defers the reply and catches everything. No
   exception escapes without becoming a message; silence is the worst failure mode
   for a bot.
5. **Frozen models with no setters and no calculations**, which turns "the bot
   computes nothing" into structure instead of a promise.
6. **Server replies, server order.** Rankings, feeds and search results are shown
   in the order the API sends them.

## Tech stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.11+ |
| Discord | [discord.py](https://github.com/Rapptz/discord.py) 2 (slash commands, views, modals) |
| HTTP | [httpx](https://www.python-httpx.org/) (one shared async client) |
| Configuration | python-dotenv, validated at boot |
| Tests | pytest with `httpx.MockTransport`; views tested without a gateway |
| Quality | Ruff, mypy (strict on `myrank/`) |
| Infrastructure | systemd on the API's VM |

On Python 3.13+, `requirements.txt` also installs `audioop-lts`: discord.py imports
a module that left the standard library, even though the bot uses no voice.

## Security

- **No user login, no JWT.** Every request carries a fixed service key and the
  Discord ID of whoever ran the command; the API resolves the MyRank account:

  ```
  X-Bot-Key:    <MYRANK_BOT_API_KEY>
  X-Discord-Id: <interaction.user.id>
  ```

- **The key only opens a closed list of routes** (`BOT_ROUTES` in the backend's
  `BotAuthenticationFilter`), granted per route and method, never "everything".
  Authentication, account deletion and session revocation are never on the list.
  Anything outside it returns 403, which the bot logs as a configuration error.
- **Linking is done on the site.** In Settings, "Connect Discord" links Discord to
  the signed-in account, whatever its sign-in method. One Discord account belongs to
  one MyRank account, and there is no linking command in the bot.
- **Rate limits per Discord user**, enforced by the API.
- **Only the user who ran a command can use its buttons**; pages and selects lock
  for everyone else and switch themselves off after a while. Anything that deletes
  asks for confirmation first.
- **No message content.** The bot runs with no privileged intents and reads no
  messages; it only answers slash commands.
- **Secrets never in logs.** `Settings.__repr__` masks the token and the key, and
  API errors become generic messages with the details only in the log.

## Running locally

Requirements: Python 3.11+, and the
[backend](https://github.com/guiGocksAfK/MyRank-backend) running with the same
`MYRANK_BOT_API_KEY`.

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then fill in DISCORD_TOKEN and MYRANK_BOT_API_KEY
python bot.py
```

Set `DISCORD_GUILD_ID` in development: syncing commands to one server is instant,
while the global sync can take up to an hour.

To use the bot, sign in on the site and use **Connect Discord** in Settings. Until
then, every command answers that the Discord account is not linked.

### Tests

The tests need no network and no Discord:

```bash
pytest          # tests
ruff check .    # lint
mypy .          # types
```

## Deploy

Same VM as the API. On the VM, the code lives in `/opt/myrank-discord-bot`, run by
a dedicated `myrankbot` user, with the `.env` set to permission `600`:

```bash
sudo cp myrank-bot.service /etc/systemd/system/
sudo systemctl enable --now myrank-bot
journalctl -u myrank-bot -f
```

Updates are `git pull` followed by `sudo systemctl restart myrank-bot`. The API on
the VM needs the same `MYRANK_BOT_API_KEY` in its own `.env`; without it the bot
filter stays off and every bot request gets a 401.

## Documentation

| Document | Covers |
|---|---|
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | What is done, what is pending and what is still to be decided |
| [`docs/decisoes.md`](docs/decisoes.md) | Scope, allowed routes and behavior decisions, and why |

## Environment variables

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Bot token from the Discord Developer Portal. |
| `MYRANK_API_URL` | API base URL. `http://localhost:8080/api` in development, `https://myrank.duckdns.org/api` in production. |
| `MYRANK_BOT_API_KEY` | Shared secret; must match the API's `MYRANK_BOT_API_KEY`. |
| `DISCORD_GUILD_ID` | Optional. Syncs commands to one server only (development). Leave empty in production. |
| `LOG_LEVEL` | Optional. Defaults to `INFO`. |

## Project structure

```
bot.py              entry point: settings, API client, cogs, command sync
myrank/             API layer, no discord.py imports
├── config.py       settings validated at boot, secrets masked in repr
├── api.py          MyRankClient: one async client, headers, status to exception
├── errors.py       NotLinkedError, RateLimitedError, ApiError, ApiUnavailableError
├── models.py       frozen dataclasses for works, tables and profiles
├── media.py        media choice to search endpoint and new-work payload
├── works.py        partial payloads for /manage
├── rankings.py     ranking and creators models
├── social.py       feed, profiles, reactions and comments models
├── insights.py     notifications and AI Insights models
└── account.py      account model and profile diff for /config
ui/                 the only place that imports discord.py
├── embeds.py       gold theme for works, tables, rankings and achievements
├── errors.py       exception to embed, and the @guarded decorator
├── views.py        pagination, search results, selects, confirmation, /manage
├── modals.py       work modals (score, manual add, details, custom fields)
├── tables.py       /tabela screens
├── social.py       social screens (profile, people, requests, feed, takes, comments)
├── social_embeds.py
├── insights.py     /notificacoes and /insights screens
└── config.py       /config screen and profile modal
cogs/               one cog per command group
tests/              client tested with httpx.MockTransport, views without a gateway
docs/               roadmap and decisions (Portuguese)
myrank-bot.service  systemd unit for the VM
```

## License

© 2026 Guilherme Gocks. All rights reserved.
This source code is shared for portfolio purposes only and may not be copied, modified or redistributed without permission.
