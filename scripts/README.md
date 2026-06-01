# scripts/ — Pipeline d'enrichissement biblio-bd

## ⛔ RÈGLE ABSOLUE

**Ne jamais faire de requêtes directes vers `bedetheque.com` depuis le serveur OpenClaw.**
Le serveur cloud est détecté et banni immédiatement (déjà arrivé 3 fois).
**Tout passe exclusivement par `bedetheque_enricher.py`.**

---

## Pipeline complet

### Étape 1 — Extraire les albums incomplets

```bash
cd biblio-bd/
python3 scripts/extract_missing.py
# → génère albums_to_enrich.json
```

### Étape 2 — Enrichir via Bédéthèque

```bash
cd biblio-bd/
BRAVE_API_KEY=BSAL408Rf_xt9rKvrvixglai9TOUGJW \
python3 scripts/bedetheque_enricher.py \
  --input albums_to_enrich.json \
  --output albums_enriched.json
```

Ce script gère automatiquement :
- Pauses aléatoires **15 à 35 secondes** entre chaque requête
- Cache persistant (`bedetheque_cache.json`) — ne refait jamais une requête déjà faite
- Headers navigateur réalistes (Chrome/Linux)
- Brave Search API pour trouver les URLs sans scraper directement
- Fallback sur l'API native Bédéthèque si Brave ne trouve pas

### Étape 3 — Fusionner et pusher

```bash
cd biblio-bd/
python3 scripts/merge.py --enriched albums_enriched.json
# → met à jour data.json, copie les images, push sur GitHub
```

Option `--no-push` pour tester sans pousser.

---

## Workflow photo d'étagère

1. Denis envoie une photo
2. Maurice extrait visuellement les albums → vérifie `data.json` → génère `albums_to_enrich.json`
3. Maurice lance **`bedetheque_enricher.py`** (étape 2 ci-dessus)
4. Maurice lance **`merge.py`** (étape 3 ci-dessus)

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `bedetheque_enricher.py` | Script principal d'enrichissement (ne pas modifier) |
| `extract_missing.py` | Génère `albums_to_enrich.json` depuis `data.json` |
| `merge.py` | Fusionne `albums_enriched.json` → `data.json` + push |
