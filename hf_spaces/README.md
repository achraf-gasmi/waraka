---
title: Waraka STR Agent
emoji: 🏦
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.40.0
app_file: app.py
pinned: false
license: mit
short_description: Agent IA de rédaction de déclarations de soupçon goAML (CTAF)
---

# Waraka — Agent de Déclaration de Soupçon

Système d'aide à la rédaction de déclarations de soupçon (STR) conforme goAML pour les banques tunisiennes.

Cette application exécute le **pipeline Waraka réel** : le même agent LangGraph
(`graph/str_graph.py`), les mêmes outils (`tools/goaml_tool.py`, `tools/ner_tool.py`,
`tools/sanctions_tool.py`) et les mêmes modèles Pydantic (`models/schemas.py`) que le
backend FastAPI — vendorés directement dans `hf_spaces/` pour ce déploiement. Aucun
backend FastAPI, aucune base de données : `api/main.py` est le seul module qui écrit
dans PostgreSQL, et il n'est pas utilisé ici.

Le backend LLM est sélectionné via `agents/str_agent.py` (`LLM_PROVIDER`, lu à chaque
appel) ; ce déploiement force `LLM_PROVIDER=gemini` pour utiliser le palier gratuit de
l'API Google Gemini. Il n'existe pas de mode démonstration : une clé `GEMINI_API_KEY`
valide est requise pour que l'application fonctionne.

Le filtrage sanctions (`tools/sanctions_tool.py`) est optionnel — sans
`OPENSANCTIONS_API_KEY`, il est simplement ignoré (aucune entité n'est marquée comme
sanctionnée), sans erreur.

## Configuration (Secrets HF Spaces)

Définissez dans **Settings → Variables and secrets** :

```
GEMINI_API_KEY=AIza...
```

Optionnel (filtrage sanctions OpenSanctions) :
```
OPENSANCTIONS_API_KEY=...
```

Obtenez une clé Gemini gratuite sur [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).

Sans `GEMINI_API_KEY`, l'application affiche un message d'erreur expliquant comment la
configurer et s'arrête — aucune donnée fictive n'est affichée.

## Structure vendorée

```
hf_spaces/
├── app.py              # Interface Streamlit -- appelle run_str_graph() directement
├── agents/str_agent.py  # Prompts + dispatch LLM_PROVIDER (anthropic | gemini)
├── graph/str_graph.py    # Agent LangGraph -- 5 noeuds, identique au backend
├── tools/                # goaml_tool, ner_tool, sanctions_tool -- identiques au backend
└── models/schemas.py      # Modeles Pydantic -- identiques au backend
```

Ces fichiers sont copiés depuis la racine du projet. Toute correction apportée au
pipeline central (`agents/`, `graph/`, `tools/`, `models/`) doit être répliquée ici.

## Contexte réglementaire

- Loi organique tunisienne n° 2015-26 (modifiée par 2019-9)
- Circulaire BCT n° 2025-17 — obligation de déclaration via goAML
- CTAF — Commission Tunisienne des Analyses Financières
