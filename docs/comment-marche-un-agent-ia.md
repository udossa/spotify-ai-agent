# Comment marche un agent IA ?

*Expliqué avec le code de ce repo comme illustration.*

Ce document explique les concepts fondamentaux d'un agent IA — boucle de
raisonnement, outils, RAG, MCP — en s'appuyant sur du code réel que tu peux
lire, lancer et modifier : celui de ce projet.

---

## 1. LLM seul vs agent : la différence fondamentale

Un **LLM seul** est une fonction texte → texte. Tu lui demandes « crée-moi une
playlist workout », il te répond… du texte : une liste de titres imaginée, avec
probablement des morceaux inventés, et **rien n'est créé nulle part**.

Un **agent** est un LLM placé dans une boucle et équipé d'**outils** — des
fonctions qu'il peut décider d'appeler. Il peut alors :

1. **percevoir** — lire les résultats de ses actions ;
2. **raisonner** — décider quoi faire ensuite ;
3. **agir** — appeler un outil qui a un effet réel (ici : l'API Spotify).

```
LLM seul  :  question ──► réponse (du texte, point final)

Agent     :  question ──► raisonne ──► agit (outil) ──► observe ──► raisonne ──► ... ──► réponse
                              ▲                            │
                              └────────────────────────────┘
                                     la BOUCLE
```

Dans ce repo, la frontière est visible dans l'arborescence même :

- [`app/`](../app) — le **raisonnement** (l'agent) ;
- [`mcp_spotify_server/`](../mcp_spotify_server) — les **actions** (les outils) ;
- [`data/`](../data) — la **connaissance** (le RAG).

## 2. Anatomie de notre agent : les 4 briques

```
┌────────────────────────────────────────────────────┐
│                    L'AGENT                         │
│                                                    │
│  ① LLM (le "cerveau")          app/agent.py        │
│  ② Prompt système (la mission) app/prompts.py      │
│  ③ Boucle d'orchestration      app/graph.py        │
│  ④ Outils :                                        │
│      • connaissance (RAG)      app/rag.py          │
│      • actions (MCP Spotify)   mcp_spotify_server/ │
└────────────────────────────────────────────────────┘
```

### ① Le LLM — celui qui décide

[`app/agent.py`](../app/agent.py) instancie le modèle. C'est un composant
interchangeable (OpenAI, Anthropic…) : l'agent n'est pas « un modèle », c'est
une **architecture autour** d'un modèle.

```python
model = init_chat_model(settings.llm_model, temperature=0.4)
```

### ② Le prompt système — la mission et les règles

[`app/prompts.py`](../app/prompts.py) est le seul endroit où vit la « politique »
de l'agent : dans quel ordre travailler, quelles règles respecter, quoi ne
jamais faire. Extrait :

```text
1. Appelle l'outil `search_music_knowledge` [...] AVANT toute action Spotify.
...
- N'invente jamais d'identifiants ou d'URIs Spotify : utilise uniquement
  ceux renvoyés par les outils.
```

Cette dernière règle combat le défaut n°1 des LLM : **l'hallucination**. Sans
elle, le modèle pourrait « inventer » des URIs Spotify plausibles mais faux.
Un bon agent est conçu pour que la vérité vienne des outils, pas du modèle.

### ③ La boucle — LangGraph

[`app/graph.py`](../app/graph.py) assemble le tout en un **graphe d'états** :

```python
graph = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)
```

Le graphe compilé a cette forme (tu peux l'afficher toi-même, voir §3) :

```
__start__ ──► agent ──► (décision)
                │            │
                │      appel d'outil ?
                │            ▼
                │         tools ──► (résultat renvoyé à l'agent)
                │            │
                │            └──────► agent (re-raisonne)
                ▼
             __end__  (quand l'agent produit une réponse finale)
```

C'est le pattern **ReAct** (*Reasoning + Acting*) : à chaque tour, le LLM
choisit entre « appeler un outil » et « répondre ». La boucle s'arrête quand il
répond.

### ④ Les outils — les mains de l'agent

Un outil = un **nom**, une **description**, un **schéma d'arguments**. C'est
tout ce que le LLM voit. Exemple dans
[`mcp_spotify_server/server.py`](../mcp_spotify_server/server.py) :

```python
@mcp.tool()
def search_tracks(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Recherche des morceaux sur Spotify.

    query : requête. Filtres valides uniquement : `genre:`, `artist:`, ...
    """
```

**La docstring n'est pas un commentaire : c'est une interface.** Le LLM la lit
pour décider quand et comment appeler l'outil. Nous l'avons appris à nos
dépens : notre première version ne précisait pas les filtres valides, et le
LLM inventait `energy:high` → erreur 400 de l'API. La correction n'était pas
du code, mais **une meilleure docstring** (+ une règle dans le prompt).

## 3. La boucle en action : une trace réelle

Voici ce qui s'est réellement passé lors d'un run de ce projet avec la demande
*« Crée une playlist "Afrobounce Workout" de 20 morceaux mêlant Afro, Rap et
Electronica avec une énergie élevée »* :

| Tour | Décision de l'agent | Outil appelé | Observation |
|---|---|---|---|
| 1 | « Je dois d'abord connaître les préférences » | `search_music_knowledge("afro rap electronica énergie")` | Règles : max 2 titres/artiste, répartition équitable des genres… |
| 2-7 | « Je cherche des titres pour chaque genre » | `search_tracks("genre:afrobeats year:2022-2025")`, `search_tracks("genre:rap ...")`, … | ~10 titres par recherche |
| 8 | « J'ai un vivier suffisant, je crée la playlist » | `create_playlist("Afrobounce Workout", ...)` | `{id: "2YRT...", url: "https://open.spotify.com/..."}` |
| 9 | « J'ajoute ma sélection » | `add_tracks_to_playlist("2YRT...", [uris])` | `{added: 20}` |
| 10 | « Terminé » → **réponse finale** | *(aucun)* | « Playlist créée : [lien] » |

Chaque ligne est un tour de boucle : le LLM reçoit tout l'historique
(messages + résultats d'outils) et décide de la suite. Personne n'a codé cette
séquence — elle **émerge** du prompt, des outils disponibles et de la demande.

Tu peux observer ces tours en direct : lance `uv run spotify-agent` et regarde
les logs JSON sur stderr (`CallToolRequest` = un appel d'outil).

**Et quand ça rate ?** Pendant le développement, l'API Spotify renvoyait des
`403` à la création (endpoints supprimés en février 2026, cf. README). L'agent
n'a pas planté : il a **observé l'erreur, re-raisonné**, et proposé la liste de
titres en texte à défaut de pouvoir créer la playlist. C'est la robustesse
propre aux agents : l'erreur d'un outil est une observation comme une autre.

## 4. Le RAG — donner une mémoire documentaire à l'agent

**Problème** : le LLM ne connaît ni tes goûts, ni tes règles de playlists. On
pourrait tout coller dans le prompt, mais ça ne passe pas à l'échelle (et tout
n'est pas pertinent pour chaque demande).

**Solution** : le **RAG** (*Retrieval-Augmented Generation*) — stocker la
connaissance dehors, et n'en récupérer que la partie **pertinente** au moment
utile. Implémenté dans [`app/rag.py`](../app/rag.py) en trois temps :

```
INGESTION (une fois, `spotify-agent --ingest`)
  data/*.md ──découpage──► chunks ──embedding──► vecteurs ──► ChromaDB

RETRIEVAL (à chaque requête de l'agent)
  "afro énergie workout" ──embedding──► vecteur ──similarité──► les 4 chunks
                                                                les + proches
```

1. **Découpage** : chaque fichier de [`data/`](../data) est coupé en morceaux
   (~1000 caractères) — `MarkdownTextSplitter`.
2. **Embedding** : chaque morceau devient un vecteur numérique qui capture son
   *sens* (deux textes proches en sens → vecteurs proches).
3. **Retrieval** : la question de l'agent est vectorisée à son tour, et on
   récupère les chunks les plus proches.

Point d'architecture important : **le RAG est exposé à l'agent comme un outil
ordinaire** (`search_music_knowledge`). L'agent ne « fait » pas du RAG — il
appelle un outil de recherche, comme il appelle Spotify. Uniformité = simplicité.

## 5. MCP — des outils standardisés et découplés

On aurait pu écrire les fonctions Spotify directement dans `app/`. Pourquoi un
**serveur séparé** parlant **MCP** (*Model Context Protocol*) ?

MCP est un protocole standard (à la USB) entre les applications IA et leurs
outils. Le serveur déclare ses outils ; n'importe quel client compatible peut
les découvrir et les appeler.

```
app/mcp_client.py                      mcp_spotify_server/server.py
┌─────────────────┐    stdio (JSON)    ┌──────────────────────┐
│  Client MCP     │ ◄────────────────► │  Serveur MCP         │
│  (dans l'agent) │   list_tools,      │  @mcp.tool()         │──► API Spotify
└─────────────────┘   call_tool        │  search_tracks, ...  │
                                       └──────────────────────┘
```

Côté client ([`app/mcp_client.py`](../app/mcp_client.py)), trois lignes
suffisent : lancer le serveur, découvrir ses outils, les convertir en outils
LangChain. Ce découplage apporte :

- **Réutilisabilité** — ce même serveur Spotify marcherait avec Claude
  Desktop, un autre framework d'agent, un autre projet.
- **Remplaçabilité** — un serveur MCP Apple Music avec les mêmes noms d'outils,
  et l'agent fonctionne sans changer une ligne de `app/`.
- **Frontière de sécurité** — les credentials Spotify vivent dans le process
  serveur, pas dans le process de raisonnement.

## 6. La règle d'or : séparer raisonnement, connaissance et action

Le brief de ce projet impose : *« Aucune logique métier ne doit être
implémentée dans le serveur MCP »*. C'est LE principe d'architecture des
agents :

| Couche | Rôle | Ici | Contient | Ne contient jamais |
|---|---|---|---|---|
| **Raisonnement** | décider | `app/prompts.py` + LLM | règles métier, stratégie | secrets, appels API directs |
| **Connaissance** | savoir | `data/` + `app/rag.py` | préférences, règles documentées | logique exécutable |
| **Action** | faire | `mcp_spotify_server/` | appels API bruts, auth | décisions, sélection, règles |

Test concret : la règle « maximum 2 titres par artiste » est dans
[`data/playlist_rules.md`](../data/playlist_rules.md) (connaissance, récupérée
par RAG) et appliquée par le LLM (raisonnement). Elle n'est **pas** codée dans
`add_tracks_to_playlist`, qui ajoute bêtement ce qu'on lui donne.

Pourquoi c'est crucial ? Pour changer la règle, tu édites un fichier markdown
et ré-indexes — **zéro code modifié**. Et l'outil reste réutilisable pour un
agent qui aurait d'autres règles.

## 7. Les limites — ce qu'un agent ne garantit pas

Un agent reste probabiliste. Observé sur ce projet même :

- **Respect approximatif des consignes** : demandé 20 titres, obtenu 26 lors
  d'un run. Correctif : durcir le prompt (« EXACTEMENT le nombre demandé —
  compte avant d'ajouter »). Pour une garantie absolue, il faudrait un nœud de
  validation dans le graphe (du code, pas du prompt).
- **Invention d'arguments d'outils** : le filtre `energy:high` qui n'existe
  pas. Correctif : contraindre via la docstring de l'outil + le prompt.
- **Coût et latence** : chaque tour de boucle = un appel LLM. Notre run en
  fait ~10. Un agent mal borné peut boucler cher.

La conception d'un agent, c'est arbitrer en permanence entre **souplesse**
(laisser le LLM décider — dans le prompt) et **garanties** (contraindre — dans
le code / le graphe).

## 8. Pour aller plus loin avec ce repo

Exercices par difficulté croissante :

1. **Connaissance** — remplace `data/*.md` par tes goûts, ré-indexe
   (`--ingest --reset`), observe comment les playlists changent.
2. **Prompt** — modifie une règle dans `prompts.py` (ex. « toujours finir par
   un titre calme ») et vérifie qu'elle est suivie.
3. **Outil** — ajoute `remove_tracks_from_playlist` au serveur MCP (même
   pattern que `add_tracks_to_playlist`) : l'agent sait alors *corriger* une
   playlist.
4. **Graphe** — remplace `create_react_agent` par un graphe manuel avec un
   nœud de validation qui recompte les titres avant l'ajout (voir la doc
   LangGraph sur `StateGraph`).
5. **Multi-agents** — un agent « curateur » qui critique la sélection d'un
   agent « chercheur » avant la création (l'évolution §10 du brief).

---

*Concepts couverts : agent, boucle ReAct, function calling, hallucination,
RAG (ingestion / embedding / retrieval), MCP, séparation des responsabilités.*
