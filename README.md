# Bédéthèque (biblio-bd)

## Contexte
Application web de type PWA (Progressive Web App) pour gérer la collection de bandes dessinées de Denis. Hébergée de manière statique sur GitHub Pages (dépôt `sined79/biblio-bd`).

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
- **Script :** `scripts/enrich_stealth.py`.
- **Fonctionnement :** Exécuté par le cron `bd_cover_scraper` toutes les 30 minutes. Il cherche une BD sans couverture dans le JSON, interroge furtivement les moteurs de recherche pour trouver la page *Bedetheque*, télécharge l'image, extrait les métadonnées (scénariste, dessinateur, ISBN, synopsis), met à jour le JSON et pousse le tout sur GitHub.
- **Règle absolue :** Ne pas faire de requêtes massives pour éviter le bannissement de l'IP. Toujours procéder tome par tome, espacé dans le temps.