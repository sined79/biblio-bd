#!/usr/bin/env python3
"""
merge.py — Étape 3 du pipeline biblio-bd

Fusionne `albums_enriched.json` (sortie de bedetheque_enricher.py)
dans `data.json`, copie les nouvelles images, et pousse sur GitHub.

Usage:
    cd biblio-bd/
    python3 scripts/merge.py --enriched albums_enriched.json

Options:
    --enriched  Fichier JSON enrichi (défaut: albums_enriched.json)
    --data      Fichier data cible   (défaut: data.json)
    --no-push   Ne pas pusher sur GitHub après fusion
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data.json"
IMAGES_DIR = ROOT / "images"


def load_json(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(data: list, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def album_key(album: dict) -> str:
    return f"{album.get('serie', '').strip()}|{str(album.get('tome', '')).strip()}"


def merge_album(existing: dict, enriched: dict) -> dict:
    """
    Fusionne les données enrichies dans l'album existant.
    Ne remplace un champ existant QUE si le nouveau est non vide.
    """
    merged = dict(existing)
    FIELDS = [
        "titre", "auteurs", "editeur", "annee", "isbn",
        "scenariste", "dessinateur", "scenaristes", "dessinateurs",
        "synopsis", "cover_url", "bedetheque_url", "collection",
    ]
    for field in FIELDS:
        new_val = enriched.get(field)
        if new_val and not existing.get(field):
            merged[field] = new_val

    # cover (chemin local) : copier l'image si elle existe dans enriched
    new_cover = enriched.get("cover", "")
    if new_cover and Path(new_cover).exists() and not existing.get("cover"):
        dest = IMAGES_DIR / Path(new_cover).name
        if not dest.exists():
            shutil.copy2(new_cover, dest)
            print(f"  📁 Image copiée: {dest.name}")
        merged["cover"] = f"images/{Path(new_cover).name}"

    # needs_review : passer à False si on a enrichi
    if enriched.get("needs_review") is False:
        merged["needs_review"] = False

    return merged


def git_push(commit_msg: str) -> None:
    try:
        subprocess.run(["git", "-C", str(ROOT), "add", "data.json", "images/"],
                       check=True)
        subprocess.run(["git", "-C", str(ROOT), "commit", "-m", commit_msg],
                       check=True)
        subprocess.run(["git", "-C", str(ROOT), "push", "origin", "main"],
                       check=True)
        print("✅ Pushé sur GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Git error: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Fusionne les albums enrichis dans data.json")
    parser.add_argument("--enriched", default="albums_enriched.json",
                        help="Fichier JSON enrichi (défaut: albums_enriched.json)")
    parser.add_argument("--data", default=str(DATA_FILE),
                        help="Fichier data cible (défaut: data.json)")
    parser.add_argument("--no-push", action="store_true",
                        help="Ne pas pusher sur GitHub")
    args = parser.parse_args()

    enriched_path = Path(args.enriched)
    data_path = Path(args.data)

    if not enriched_path.exists():
        print(f"❌ Fichier introuvable: {enriched_path}", file=sys.stderr)
        sys.exit(1)

    if not data_path.exists():
        print(f"❌ Fichier introuvable: {data_path}", file=sys.stderr)
        sys.exit(1)

    existing_data = load_json(data_path)
    enriched_data = load_json(enriched_path)

    # Index existant
    existing_index = {album_key(a): a for a in existing_data}

    updated = 0
    added = 0
    skipped = 0

    for enriched_album in enriched_data:
        if enriched_album.get("needs_review"):
            print(f"  ⚠️  needs_review=True, ignoré: {enriched_album.get('serie')} t{enriched_album.get('tome')}")
            skipped += 1
            continue

        key = album_key(enriched_album)
        if key in existing_index:
            existing_index[key] = merge_album(existing_index[key], enriched_album)
            print(f"  ✏️  Mis à jour: {enriched_album.get('serie')} t{enriched_album.get('tome')}")
            updated += 1
        else:
            existing_index[key] = enriched_album
            print(f"  ➕ Ajouté: {enriched_album.get('serie')} t{enriched_album.get('tome')}")
            added += 1

    final_data = list(existing_index.values())
    save_json(final_data, data_path)

    print()
    print(f"✅ Fusion terminée — {updated} mis à jour, {added} ajoutés, {skipped} ignorés.")
    print(f"   Total: {len(final_data)} albums dans {data_path}")

    if not args.no_push:
        msg = f"Enrich: {updated} updated, {added} added via bedetheque_enricher"
        git_push(msg)


if __name__ == "__main__":
    main()
