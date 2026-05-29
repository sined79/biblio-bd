#!/usr/bin/env python3
"""
Enrich biblio-bd: fetch missing cover_url and synopsis via Brave Search.
Run from biblio-bd/ directory.
"""

import json, os, re, time, urllib.request, urllib.parse

BRAVE_KEY = "BSAL408Rf_xt9rKvrvixglai9TOUGJW"
DATA_FILE = "data.json"
IMAGES_DIR = "images"

def brave_web(query, count=3):
    enc = urllib.parse.quote(query)
    url = f"https://api.search.brave.com/res/v1/web/search?q={enc}&count={count}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_KEY
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as e:
        print(f"  web error: {e}")
        return {}

def brave_images(query, count=5):
    enc = urllib.parse.quote(query)
    url = f"https://api.search.brave.com/res/v1/images/search?q={enc}&count={count}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_KEY
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as e:
        print(f"  img error: {e}")
        return {}

def find_cover_url(serie, tome, titre):
    """Search for bedetheque cover URL."""
    query = f'"{titre}" "{serie}" bedetheque couverture'
    data = brave_images(query)
    for r in data.get("results", []):
        src = r.get("thumbnail", {}).get("src", "")
        m = re.search(r'bedetheque\.com/media/Couvertures/Couv_(\d+)', src)
        if m:
            return f"https://www.bedetheque.com/media/Couvertures/Couv_{m.group(1)}.jpg"
        page_url = r.get("url", "")
        m2 = re.search(r'-(\d+)\.html$', page_url)
        if m2 and "bedetheque.com/BD-" in page_url:
            return f"https://www.bedetheque.com/media/Couvertures/Couv_{m2.group(1)}.jpg"
    # fallback: web search
    wdata = brave_web(f'site:bedetheque.com {serie} tome {tome} {titre}')
    for r in wdata.get("web", {}).get("results", []):
        u = r.get("url", "")
        m3 = re.search(r'-(\d+)\.html$', u)
        if m3 and "bedetheque.com/BD-" in u:
            return f"https://www.bedetheque.com/media/Couvertures/Couv_{m3.group(1)}.jpg"
    return ""

def find_synopsis(serie, tome, titre):
    """Fetch synopsis from bedetheque or bdgest."""
    # Try bedetheque first via web search snippet
    wdata = brave_web(f'site:bedetheque.com {serie} tome {tome} {titre} synopsis', count=3)
    for r in wdata.get("web", {}).get("results", []):
        desc = r.get("description", "").strip()
        if desc and len(desc) > 80 and "bedetheque.com" in r.get("url",""):
            return desc
    # Try bdgest
    wdata2 = brave_web(f'site:bdgest.com {serie} {titre} synopsis résumé', count=3)
    for r in wdata2.get("web", {}).get("results", []):
        desc = r.get("description", "").strip()
        if desc and len(desc) > 80:
            return desc
    # Generic fallback
    wdata3 = brave_web(f'{serie} tome {tome} {titre} résumé bande dessinée', count=3)
    for r in wdata3.get("web", {}).get("results", []):
        desc = r.get("description", "").strip()
        if desc and len(desc) > 80:
            return desc
    return ""

def download_cover(url, dest_path):
    if not url or os.path.exists(dest_path):
        return os.path.exists(dest_path)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        if len(data) > 5000:
            with open(dest_path, 'wb') as f:
                f.write(data)
            return True
    except Exception as e:
        print(f"  dl error: {e}")
    return False

def main():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    os.makedirs(IMAGES_DIR, exist_ok=True)

    needs_cover = [a for a in data if not a.get("cover_url", "")]
    needs_synopsis = [a for a in data if not a.get("synopsis", "")]

    print(f"Missing cover_url: {len(needs_cover)}")
    print(f"Missing synopsis: {len(needs_synopsis)}")

    changed = 0

    # Process covers
    for album in needs_cover:
        serie = album.get("serie", "")
        tome = str(album.get("tome", ""))
        titre = album.get("titre", "")
        print(f"\n[COVER] {serie} t{tome} — {titre}")
        url = find_cover_url(serie, tome, titre)
        if url:
            album["cover_url"] = url
            # Download
            slug = album.get("cover", "")
            if slug:
                dest = os.path.join(IMAGES_DIR, os.path.basename(slug))
                ok = download_cover(url, dest)
                print(f"  → {url} {'✓' if ok else '(dl failed)'}")
            changed += 1
        else:
            print(f"  → not found")
        time.sleep(0.5)

    # Process synopsis
    for album in needs_synopsis:
        if album.get("synopsis", ""):
            continue
        serie = album.get("serie", "")
        tome = str(album.get("tome", ""))
        titre = album.get("titre", "")
        print(f"\n[SYNOPSIS] {serie} t{tome} — {titre}")
        synopsis = find_synopsis(serie, tome, titre)
        if synopsis:
            album["synopsis"] = synopsis
            print(f"  → {synopsis[:80]}...")
            changed += 1
        else:
            print(f"  → not found")
        time.sleep(0.5)

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done — {changed} fields enriched, {len(data)} total albums.")

if __name__ == "__main__":
    main()
