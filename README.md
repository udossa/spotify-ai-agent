# Spotify AI Agent 🎧

Agent IA qui crée des playlists Spotify personnalisées à partir d'une intention
en langage naturel :

> « Crée une playlist *Afrobounce Workout* de 20 morceaux mêlant Afro, Rap et
> Electronica avec une énergie élevée. »

L'agent comprend la demande, consulte une base de connaissance personnelle
(**RAG**), cherche des titres sur Spotify via un **serveur MCP**, sélectionne
les morceaux en appliquant des règles métier, crée la playlist et retourne le
lien.

**Stack** : LangGraph · LangChain · MCP · ChromaDB · spotipy · uv

```
Utilisateur
     │
     ▼
   CLI (app/main.py)
     │
     ▼
 LangGraph Agent ──┬── RAG (ChromaDB) ← data/*.md
                   │
                   └── MCP Spotify (stdio) → Spotify Web API
```

📖 **Pour comprendre comment fonctionne un agent IA** (boucle de raisonnement,
outils, RAG, MCP) avec ce code comme illustration :
[docs/comment-marche-un-agent-ia.md](docs/comment-marche-un-agent-ia.md)

---

## 1. Prérequis (à partir de zéro)

### 1.1. Installer uv

[uv](https://docs.astral.sh/uv/) gère Python **et** les dépendances — pas
besoin d'installer Python séparément, uv télécharge la bonne version tout seul.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Vérifie : `uv --version`.

### 1.2. Comptes nécessaires

- Un compte **OpenAI** (LLM + embeddings) — §2.1
- Un compte **Spotify** (gratuit ou premium) — §2.2

## 2. Obtenir les accès

### 2.1. Clé API OpenAI

1. Crée / connecte-toi à un compte sur [platform.openai.com](https://platform.openai.com).
2. Ajoute un moyen de paiement dans *Settings → Billing* (facturation à
   l'usage ; `gpt-4o-mini` + `text-embedding-3-small` coûtent quelques
   centimes pour ce projet).
3. Va dans [API keys](https://platform.openai.com/api-keys) → *Create new
   secret key*.
4. Copie la clé (`sk-...`) — elle n'est affichée qu'une fois — pour
   `OPENAI_API_KEY` dans `.env` (§3).

> Pour utiliser un autre fournisseur (ex. Anthropic), voir
> [Choix par défaut](#choix-par-défaut-modifiables).

### 2.2. App Spotify

L'agent agit sur un vrai compte Spotify via OAuth. Sur le
[Dashboard développeur Spotify](https://developer.spotify.com/dashboard) :

1. **Connecte-toi avec le compte Spotify que l'agent utilisera** — le
   créateur de l'app est autorisé automatiquement, c'est le chemin le plus
   simple.
2. **Créer l'app** : *Create app* → nom + description, coche *Web API*.
3. **Redirect URI** (obligatoire, sinon l'auth échoue) : dans *Settings →
   Edit*, ajoute exactement `http://127.0.0.1:8888/callback` puis *Save*.
4. **Récupérer les identifiants** : *Settings* → *Client ID*, puis *View
   client secret*.
5. *(Seulement si le compte utilisateur ≠ créateur de l'app)* : *Settings →
   User Management → Add user* avec le nom + l'**email exact** du compte.

   > Une app est en **mode Développement** par défaut : seuls le créateur et
   > les comptes ajoutés ici (max 5) peuvent utiliser l'app. Sinon :
   > `403 — the user may not be registered`.

Scopes demandés par le serveur MCP : `playlist-modify-public` et
`playlist-modify-private` (le minimum pour créer et remplir des playlists).

## 3. Installation

```bash
git clone <url-du-repo> && cd spotify-ai-agent   # ou télécharge le dossier
uv sync                                          # venv + dépendances (+ dev)
cp .env.example .env
```

Ouvre `.env` et renseigne :

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Clé API OpenAI (§2.1) |
| `SPOTIPY_CLIENT_ID` | *Client ID* de l'app Spotify (§2.2) |
| `SPOTIPY_CLIENT_SECRET` | *Client secret* de l'app Spotify (§2.2) |
| `SPOTIPY_REDIRECT_URI` | Doit correspondre au Redirect URI configuré (§2.2) |
| `LLM_MODEL` | Modèle, ex. `openai:gpt-4o-mini` |

## 4. Indexer le RAG

La base de connaissance (`data/*.md` : profil musical, règles de playlist,
artistes, genres) doit être indexée une fois dans ChromaDB :

```bash
uv run spotify-agent --ingest          # option --reset pour repartir de zéro
```

Personnalise ensuite les fichiers de `data/` avec **tes** goûts, puis
ré-indexe.

## 5. Lancer l'agent

```bash
# Sans argument : l'exemple Afrobounce Workout du brief
uv run spotify-agent

# Ou ta propre intention :
uv run spotify-agent "Crée une playlist chill de 15 morceaux soul et jazz pour le soir"
```

Au **premier lancement**, le navigateur s'ouvre une fois pour autoriser l'accès
Spotify (le token est ensuite mis en cache dans `.cache`). L'agent raisonne
(les logs JSON sur stderr montrent les appels d'outils), crée la playlist sur
ton compte et affiche le lien.

## 6. Tests

```bash
uv run pytest        # tests unitaires, sans réseau ni clé API
```

## Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `Missing credentials` (OpenAI) | `.env` absent ou incomplet | Vérifie `cp .env.example .env` et `OPENAI_API_KEY` |
| `403 — the user may not be registered` | Compte non autorisé sur l'app (mode Développement) | §2.2 étape 5, puis `rm -f .cache` et relance |
| `403 Forbidden` persistant | Token en cache émis pour un autre compte/app | `rm -f .cache` puis relance : le navigateur redemande le consentement — connecte-toi avec le bon compte |
| `400 Invalid limit` sur la recherche | Depuis **février 2026**, `/search` plafonne à 10 résultats | Déjà géré dans le serveur MCP (clamp à 10) |
| Le navigateur ne s'ouvre pas à l'auth | Environnement headless | Copie l'URL affichée dans le terminal, ouvre-la, puis colle l'URL de redirection |

> ⚠️ **Changements API Spotify de février 2026** : les endpoints
> `POST /users/{id}/playlists` et `POST /playlists/{id}/tracks` ont été
> supprimés (remplacés par `POST /me/playlists` et `POST /playlists/{id}/items`)
> et la recherche est plafonnée à 10 résultats. Ce projet utilise les nouveaux
> endpoints ; les bibliothèques ou tutoriels antérieurs à cette date renvoient
> des `403`/`400` trompeurs.

## Structure

```
spotify-ai-agent/
├── app/                      # L'AGENT (raisonnement + orchestration)
│   ├── config.py             #   settings (.env) + logging JSON
│   ├── prompts.py            #   prompt système (le "cerveau" déclaratif)
│   ├── rag.py                #   ingestion + retrieval ChromaDB
│   ├── mcp_client.py         #   lance le serveur MCP, charge ses outils
│   ├── agent.py              #   LLM + agrégation des outils
│   ├── graph.py              #   graphe LangGraph (boucle agent ⇄ outils)
│   └── main.py               #   CLI
├── mcp_spotify_server/       # LES OUTILS (actions Spotify, zéro logique métier)
│   └── server.py
├── data/                     # LA CONNAISSANCE (RAG) — à personnaliser
│   ├── music_profile.md
│   ├── playlist_rules.md
│   ├── artists.md
│   └── genres.md
├── docs/
│   └── comment-marche-un-agent-ia.md
└── tests/
```

## Choix par défaut (modifiables)

- **LLM** : `LLM_MODEL=openai:gpt-4o-mini`. Pour Anthropic :
  `uv sync --extra anthropic` puis `LLM_MODEL=anthropic:claude-sonnet-5`
  (une clé `ANTHROPIC_API_KEY` dans `.env` ; les embeddings du RAG restent
  OpenAI).
- **Auth Spotify** : OAuth Authorization Code via spotipy, token en cache
  local `.cache` (ignoré par git).

## Évolutions possibles

Façade FastAPI · mémoire conversationnelle · recommandation basée sur
l'historique d'écoute · playlists hebdomadaires automatiques · Apple Music /
Deezer via d'autres serveurs MCP.
