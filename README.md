# coros-cli

CLI Python pour extraire vos données [Coros Training Hub](https://t.coros.com) — sommeil et (à venir) activités.

Outil non-officiel, non affilié à Coros. Utilise vos propres credentials sur votre compte.

## Install

```sh
uv sync
uv run coros --help
```

## Usage

### Login

```sh
uv run coros login
```

Stocke le token dans `~/.config/coros-cli/config.json` (permissions `0600`). Région auto-détectée (eu/us/asia/cn).

### Sommeil

```sh
# 7 derniers jours par défaut
uv run coros sleep

# Plage explicite
uv run coros sleep --from 2026-04-01 --to 2026-04-14

# Sortie JSON pour scripting
uv run coros sleep --days 30 --json | jq '.[].total_minutes'
```

## Dev

```sh
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy src         # types
```

## Comment ça marche

Deux APIs distinctes :

- **Web** (`teameuapi.coros.com`) : auth MD5(pwd), header `accesstoken`. Activités, dashboard, HRV.
- **Mobile** (`apieu.coros.com`) : obligatoire pour le sommeil. Login AES-128-CBC avec clé XOR + IV `weloop3_2015_03#` (reverse-engineered de l'APK Coros). Endpoint `POST /coros/data/statistic/daily`.

Le password en clair n'est jamais stocké : seul son hash MD5 est conservé pour le replay d'authentification.
