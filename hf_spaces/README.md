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

## Modes de fonctionnement

| Mode | Condition | Comportement |
|---|---|---|
| **API** | `WARAKA_API_URL` défini | Appel du backend FastAPI complet |
| **Direct** | `ANTHROPIC_API_KEY` défini | Pipeline Claude intégré, sans base de données |
| **Démonstration** | Aucune clé | Scénario fictif illustratif |

## Configuration (Secrets HF Spaces)

Définissez dans **Settings → Secrets** :

```
ANTHROPIC_API_KEY=sk-ant-...
```

Optionnel (pour connecter un backend complet) :
```
WARAKA_API_URL=https://your-backend.com
WARAKA_API_KEY=your-api-key
```

## Contexte réglementaire

- Loi organique tunisienne n° 2015-26 (modifiée par 2019-9)
- Circulaire BCT n° 2025-17 — obligation de déclaration via goAML
- CTAF — Commission Tunisienne des Analyses Financières
