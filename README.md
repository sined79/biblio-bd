# Bédéthèque (biblio-bd)

## Contexte
Application web de type PWA (Progressive Web App) pour gérer ma collection de bandes dessinées. Hébergée de manière statique sur GitHub Pages (dépôt `sined79/biblio-bd`).

## Stack Technique
- **Frontend :** HTML, CSS, JavaScript (Vanilla). Aucun framework lourd.
- **Bibliothèques externes (via CDN) :** Lucide Icons, Chart.js.
- **Typographie :** *Playfair Display* (Google Fonts) pour les grands titres, *Satoshi* (Fontshare) pour l'interface.
- **Persistance :** Uniquement en lecture via `data.json`. Les états modifiés par l'utilisateur (lu, note, wishlist) sont gérés en mémoire dans le navigateur (pour le moment).

## Design System & Règles UI/UX
- **Couleurs :**
  - Fond clair : `#f7f6f2` (blanc cassé chaud).
  - Accent : `#8b1a1a` (bordeaux/rouge profond) uniquement pour badges, boutons, survols. Pas de dégradés.
  - Texte principal : `#28251d`.
- **Cartes BD :**
  - Les couvertures doivent utiliser `object-fit: contain` avec un fond `#eee` ou `#f8f9fa` pour ne **jamais** rogner les illustrations (pas de `cover`).
  - L'image de couverture doit avoir un fallback SVG si elle est introuvable.
  - Pas de bordure latérale colorée sur les cartes.
- **Mode Sombre (Dark Mode) :** Implémenté via un attribut `data-theme="dark"` sur la balise `<html>`.

## Fonctionnalités Clés
1. **Bibliothèque :** Grille de cartes avec filtres complets (Recherche globale Titre/Série/Auteur/ISBN, Éditeur, Scénariste, Dessinateur, Lu, Statut).
2. **Mode "En magasin" :** Interface plein écran mobile-first ultra-épurée pour vérifier rapidement si un tome est possédé ou manquant lors d'un achat en librairie.
3. **Séries :** Vue listant les séries possédées avec une *timeline* visuelle des tomes. Détection automatique des "trous" (tomes manquants) affichés sous forme de cercles vides.
4. **Détails :** Modale latérale (Drawer) contenant le synopsis, les informations techniques, les étoiles de notation et le statut lu/non lu.
5. **Statistiques :** Graphiques Chart.js pour la répartition par éditeurs et le ratio lu/non lu.

## Structure JSON (`data.json`)
Les scripts et le front-end utilisent la structure normalisée suivante :
- `serie`, `tome`, `editeur`, `annee`, `isbn`, `synopsis`, `cover` (chemin d'image local).
- `scenaristes`, `dessinateurs`, `coloristes`, `genre` (tableaux de chaînes de caractères).
- `statut` ("possede", "wishlist", "prete").
- `lu` (booléen), `note` (0 à 5), `prete_a` (nom ou null).

## Automatisation & Backend (OpenClaw)
Puisqu'il n'y a pas d'API BD ouverte, le projet est alimenté par l'agent OpenClaw.
- **Script :** `bedetheque_enricher.py` (racine du workspace, fourni par Denis).
- **Fonctionnement :** Brave Search pour trouver les URLs Bédéthèque, puis scraping avec pauses aléatoires 15-35s, cache persistant, headers navigateur réalistes.

## ⛔ RÈGLE ABSOLUE — À LIRE AVANT TOUTE ACTION SUR LA BASE

**Ne JAMAIS faire de requêtes directes vers bedetheque.com depuis le serveur.**
Le serveur cloud OpenClaw est détecté et banni immédiatement. Denis a dû renouveler l'IP à 3 reprises à cause de cette erreur.

**Pipeline obligatoire — photo d'étagère → biblio-bd :**

1. Extraire visuellement les albums depuis la photo (série, tome, titre)
2. Vérifier quels albums sont déjà dans `data.json`
3. Générer `albums_to_enrich.json` avec les nouveaux uniquement
4. Lancer **exclusivement** `bedetheque_enricher.py` :
   ```bash
   cd /home/innovation_etnic_be/.openclaw/workspace/biblio-bd
   BRAVE_API_KEY=BSAL408Rf_xt9rKvrvixglai9TOUGJW \
   python3 /home/innovation_etnic_be/.openclaw/workspace/bedetheque_enricher.py \
     --input albums_to_enrich.json \
     --output albums_enriched.json
   ```
5. Merger `albums_enriched.json` dans `data.json` + copie images + push GitHub

**Ne jamais improviser des requêtes directes maison, peu importe la raison.**
**Ne jamais utiliser `urllib`, `requests`, `httpx` directement vers bedetheque.com.**
Si le script échoue : déboguer le script, pas contourner.
