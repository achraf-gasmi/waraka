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

Cette application appelle directement l'API Google Gemini (gemini-1.5-flash) — sans backend
FastAPI, sans base de données, sans LangGraph. Il n'existe pas de mode démonstration : une clé
`GEMINI_API_KEY` valide est requise pour que l'application fonctionne.

## Configuration (Secrets HF Spaces)

Définissez dans **Settings → Variables and secrets** :

```
GEMINI_API_KEY=AIza...
```

Obtenez une clé gratuite sur [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
(gemini-1.5-flash dispose d'un palier gratuit).

Sans cette clé, l'application affiche un message d'erreur expliquant comment la
configurer et s'arrête — aucune donnée fictive n'est affichée.

## Contexte réglementaire

- Loi organique tunisienne n° 2015-26 (modifiée par 2019-9)
- Circulaire BCT n° 2025-17 — obligation de déclaration via goAML
- CTAF — Commission Tunisienne des Analyses Financières
