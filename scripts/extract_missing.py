#!/usr/bin/env python3
"""
extract_missing.py — Étape 1 du pipeline biblio-bd

Génère un fichier `albums_to_enrich.json` contenant tous les albums
de `data.json` qui manquent de données (isbn, annee, synopsis, cover_url, auteurs).

Usage:
    cd biblio-bd/
    python3 scripts/extract_missing.py

Sortie:
    albums_to_enrich.json  ← fichier d'entrée pour bedetheque_enricher.py
"""

import json
import sys
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data.json"
OUTPUT_FILE = Path(__file__).parent.parent / "albums_to_enrich.json"


def is_incomplete(album: dict) -> list[str]:
    """Retourne la liste des champs manquants pour un album."""
    missing = []
    if not album.get("isbn"):
        missing.append("isbn")
    if not album.get("annee"):
        missing.append("annee")
    if not album.get("synopsis"):
        missing.append("synopsis")
    if not album.get("cover_url"):
        missing.append("cover_url")
    if not album.get("auteurs") and not album.get("scenariste"):
        missing.append("auteurs")
    return missing


def main():
    if not DATA_FILE.exists():
        print(f"❌ Fichier introuvable: {DATA_FILE}", file=sys.stderr)
        sys.exit(1)

    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    incomplete = []
    for album in data:
        missing = is_incomplete(album)
        if missing:
            incomplete.append({
                "serie":   album.get("serie", ""),
                "tome":    album.get("tome", ""),
                "titre":   album.get("titre", ""),
                "auteurs": album.get("auteurs", ""),
                "_missing": missing,
            })

    # Trier par série puis tome pour lisibilité
    incomplete.sort(key=lambda a: (a["serie"], str(a["tome"])))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(incomplete, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(incomplete)} albums incomplets sur {len(data)} → {OUTPUT_FILE}")
    print()
    for a in incomplete:
        print(f"  {a['serie']} t{a['tome']} — {a['titre']} | manque: {a['_missing']}")

    print()
    print("Étape suivante :")
    print("  BRAVE_API_KEY=... python3 scripts/bedetheque_enricher.py \\")
    print("    --input albums_to_enrich.json \\")
    print("    --output albums_enriched.json")


if __name__ == "__main__":
    main()
