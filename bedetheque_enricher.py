#!/usr/bin/env python3
"""
Bédéthèque Enricher
Enrichit un fichier JSON d'albums BD avec les métadonnées de bedetheque.com

Usage:
    python bedetheque_enricher.py --input albums_input.json --output albums_output.json
"""

import argparse
import asyncio
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx
from rapidfuzz import fuzz
from tqdm import tqdm


# ─── Configuration ────────────────────────────────────────────────────────────

BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
BEDETHEQUE_BASE = "https://www.bedetheque.com"
CACHE_FILE = "bedetheque_cache.json"
IMAGES_DIR = "images"
FUZZY_THRESHOLD = 80

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


# ─── Cover download ───────────────────────────────────────────────────────────

async def download_cover(
    url: str,
    serie: str,
    tome: str,
    client: httpx.AsyncClient,
    images_dir: str = IMAGES_DIR,
) -> Optional[str]:
    """
    Télécharge l'image de couverture et la sauvegarde dans `images_dir`.
    Nomme le fichier d'après la série et le tome : serie-tome.jpg
    Retourne le chemin relatif du fichier, ou None en cas d'erreur.
    """
    if not url:
        return None

    # Construit un nom de fichier propre
    safe_serie = re.sub(r"[^a-zA-Z0-9\-]", "-", serie)
    safe_serie = re.sub(r"-+", "-", safe_serie).strip("-").lower()
    ext = url.rsplit(".", 1)[-1].split("?")[0].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        ext = "jpg"
    filename = f"{safe_serie}-t{tome}.{ext}"
    filepath = Path(images_dir) / filename

    # Ne re-télécharge pas si déjà présent
    if filepath.exists():
        return str(filepath)

    try:
        r = await client.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            filepath.write_bytes(r.content)
            return str(filepath)
        else:
            tqdm.write(f"  [Cover] HTTP {r.status_code} pour {url}")
    except Exception as e:
        tqdm.write(f"  [Cover] Erreur téléchargement {url}: {e}")
    return None


# ─── Cache helpers ─────────────────────────────────────────────────────────────

def load_cache(cache_file: str) -> dict:
    if Path(cache_file).exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_cache(cache: dict, cache_file: str) -> None:
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def cache_key(serie: str, tome: str) -> str:
    return f"{serie.strip().lower()}|{str(tome).strip()}"


# ─── 1. Brave Search ──────────────────────────────────────────────────────────

async def brave_search_bedetheque(
    titre: str, tome: str, serie: str, client: httpx.AsyncClient
) -> Optional[str]:
    """
    Interroge Brave Search API pour trouver la page bedetheque.com de l'album.
    Retourne la première URL correspondante ou None.
    """
    if not BRAVE_API_KEY:
        return None

    query = f'site:bedetheque.com "{serie}" tome {tome}'
    try:
        r = await client.get(
            BRAVE_API_URL,
            params={"q": query, "count": 5, "search_lang": "fr", "country": "FR"},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("web", {}).get("results", [])
        for result in results:
            url = result.get("url", "")
            if "bedetheque.com/BD-" in url:
                return url
    except Exception as e:
        tqdm.write(f"  [Brave] Erreur: {e}")
    return None


# ─── 2. Native Bédéthèque search (fallback) ───────────────────────────────────

async def _query_series_autocomplete(
    term: str, client: httpx.AsyncClient
) -> list:
    """Appelle l'autocomplete Bédéthèque pour un terme donné."""
    try:
        r = await client.get(
            f"{BEDETHEQUE_BASE}/ajax/series",
            params={"term": term},
            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"},
            timeout=10,
        )
        return json.loads(r.text)
    except Exception:
        return []


async def bedetheque_get_serie_id(
    serie: str,
    client: httpx.AsyncClient,
    auteurs: str = "",
) -> Optional[str]:
    """
    Utilise l'endpoint AJAX de Bédéthèque pour obtenir l'ID d'une série.
    Plusieurs stratégies de recherche sont tentées en cascade.
    """
    try:
        # Tentative 1 : nom exact via ajax/serie_id
        r = await client.get(
            f"{BEDETHEQUE_BASE}/ajax/serie_id",
            params={"SERIE": serie},
            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"},
            timeout=10,
        )
        serie_id = r.text.strip()
        if serie_id and serie_id.isdigit():
            return serie_id

        # Construction des termes de recherche à essayer
        # Pour les séries comme "La Quête de l'oiseau du temps - Avant la Quête"
        # on essaie plusieurs fragments
        # Note : l'AJAX est un préfix-search, donc les termes doivent être des
        # préfixes valides du nom de série tel qu'il apparaît sur Bédéthèque.
        search_terms = []

        # Terme 1 : 20 premiers caractères (sans article initial)
        clean = re.sub(r"^(La |Le |Les |L'|Un |Une )", "", serie, flags=re.I).strip()
        search_terms.append(clean[:20].strip())

        # Terme 2 : premier mot seulement (pour gérer les variantes orthographiques)
        first_word = clean.split()[0] if clean.split() else ""
        if first_word and len(first_word) >= 3:
            search_terms.append(first_word)

        # Terme 3 : deux premiers mots (aide pour les titres courts avec fautes)
        words_all = clean.split()
        if len(words_all) >= 2:
            search_terms.append(" ".join(words_all[:2]))

        # Terme 4 : si la série contient " - ", essayer la partie avant le tiret
        if " - " in serie:
            before_dash = serie.split(" - ")[0].strip()
            before_clean = re.sub(r"^(La |Le |Les |L'|Un |Une )", "", before_dash, flags=re.I).strip()
            search_terms.append(before_clean[:20].strip())
            # Aussi le premier mot de cette partie
            bd_first = before_clean.split()[0] if before_clean.split() else ""
            if bd_first and len(bd_first) >= 3:
                search_terms.append(bd_first)

        # Déduplique tout en conservant l'ordre
        seen_terms: set = set()
        unique_terms = []
        for t in search_terms:
            if t and t not in seen_terms and len(t) >= 3:
                seen_terms.add(t)
                unique_terms.append(t)

        # Cherche dans tous les résultats des différentes tentatives
        all_candidates: list = []
        for term in unique_terms:
            candidates = await _query_series_autocomplete(term, client)
            all_candidates.extend(candidates)

        if not all_candidates:
            return None

        # Score chaque candidat
        best_score = 0
        best_id = None
        best_label_len = 9999
        for c in all_candidates:
            label = c.get("label", "")
            # Score sur le nom de la série
            name_score = fuzz.token_set_ratio(serie.lower(), label.lower())

            # Bonus si le premier auteur apparaît dans le label de la série
            auteur_bonus = 0
            if auteurs:
                first_auteur = auteurs.split(",")[0].strip().lower()
                if first_auteur and first_auteur in label.lower():
                    auteur_bonus = 20
            # Bonus supplémentaire si le label est une correspondance FR exacte
            # (pas "en anglais", "en espagnol", etc.)
            lang_penalty = -10 if re.search(r"\ben (anglais|espagnol|italien|portugais|allemand)\b", label.lower()) else 0

            total_score = name_score + auteur_bonus + lang_penalty
            # En cas d'égalité, préférer le label le plus court (moins de qualificatifs)
            if total_score > best_score or (
                total_score == best_score and len(label) < best_label_len
            ):
                best_score = total_score
                best_id = c.get("id")
                best_label_len = len(label)

        if best_score >= FUZZY_THRESHOLD and best_id:
            return str(best_id)

    except Exception as e:
        tqdm.write(f"  [Serie ID] Erreur: {e}")
    return None


async def bedetheque_native_search(
    serie: str,
    tome: str,
    client: httpx.AsyncClient,
    titre: str = "",
    auteurs: str = "",
) -> Optional[str]:
    """
    Fallback : trouve l'URL de l'album via la page de la série.
    1. Obtient l'ID de la série (avec aide des auteurs pour disambiguïser).
    2. Scrap la page de la série pour trouver l'album au bon tome.
    3. Si le tome n'est pas trouvé, essaie un matching par titre.
    """
    serie_id = await bedetheque_get_serie_id(serie, client, auteurs=auteurs)
    if not serie_id:
        tqdm.write(f"  [Native] Serie ID non trouvé pour '{serie}'")
        return None

    # Construction du slug de série (heuristique)
    serie_slug = re.sub(r"[^a-zA-Z0-9]", "-", serie)
    serie_slug = re.sub(r"-+", "-", serie_slug).strip("-")
    series_url = f"{BEDETHEQUE_BASE}/serie-{serie_id}-BD-{serie_slug}.html"

    try:
        # On charge toute la série si possible (__10000 = tous les albums)
        full_url = f"{BEDETHEQUE_BASE}/serie-{serie_id}-BD-{serie_slug}__10000.html"
        r = await client.get(full_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            # Retente sans __10000
            r = await client.get(series_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            tqdm.write(f"  [Native] Page série inaccessible: {r.status_code}")
            return None

        # Extrait toutes les URLs d'albums avec leur numéro de tome
        # Supporte aussi les tomes négatifs (ex: -1, -2) et les hors-séries (HS1, HS2...)
        # Pattern pour tomes normaux et négatifs
        pattern_tome = re.compile(
            r'href="(https://www\.bedetheque\.com/BD-[^"#]+?-Tome-(-?\d+)-[^"#]+?\.html[l]?)"'
        )
        # Pattern pour hors-séries (HS1, HS2...)
        pattern_hs = re.compile(
            r'href="(https://www\.bedetheque\.com/BD-[^"#]+?-HS(\d+)-[^"#]+?\.html[l]?)"'
        )

        seen: set = set()
        tome_str = str(tome).strip()
        best_titre_url = None
        best_titre_score = 0

        # Si la série contient un qualificatif de sous-série (arrière boutique,
        # intégrale, etc.) ET qu'on a un titre, on préfère le matching par titre
        # plutôt que le numéro de tome (car la numérotation diffère souvent).
        # Exception : si le sous-qualificatif est "Avant la" (ex: Avant la Quête),
        # le numéro de tome dans l'input correspond à autre chose que dans la série.
        SUBSERIE_KEYWORDS = re.compile(
            r"arrière.boutique|intégrale|intégral|omnibus|hors.série|hs\b",
            re.IGNORECASE,
        )
        AVANT_LA_KEYWORDS = re.compile(r"avant.la", re.IGNORECASE)
        is_hs_type = bool(SUBSERIE_KEYWORDS.search(serie))
        is_avant_la = bool(AVANT_LA_KEYWORDS.search(serie))
        use_title_priority = bool(titre and (is_avant_la or is_hs_type))

        # Table de conversion chiffres romains → arabes
        ROMAN_TO_INT = {
            "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
            "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
        }

        def _title_score_for_url(url: str, num_found: str, separator: str) -> float:
            """Score de correspondance titre/URL."""
            if not titre:
                return 0.0
            # Slug de la partie après le numéro (ex: "Marie-12345")
            after_num = url.split(f"-{separator}{num_found}-")[-1].replace(".html", "")
            if after_num.endswith(".htm"):
                after_num = after_num[:-4]
            # Supprime le suffixe numérique (ID interne)
            after_clean = re.sub(r"-\d+$", "", after_num)

            # Slug complet du fichier sans extension et sans ID
            full_slug = url.split("/")[-1].replace(".html", "").replace(".htm", "")
            full_slug_clean = re.sub(r"-\d+$", "", full_slug)

            # Score 1 : token_set_ratio sur la partie après le numéro
            s1 = fuzz.token_set_ratio(titre.lower(), after_clean.lower().replace("-", " "))
            # Score 2 : partial_ratio sur le slug complet (utile pour HS/intégrales)
            s2 = fuzz.partial_ratio(titre.lower(), full_slug_clean.lower().replace("-", " "))
            # Score 3 : ratio direct pour les correspondances exactes courtes
            s3 = fuzz.ratio(titre.lower(), after_clean.lower().replace("-", " "))

            base_score = max(s1, s2, (s3 + s1) / 2)

            # Bonus si le numéro du tome (arabe ou romain) correspond
            # au numéro trouvé dans l'URL.
            # On cherche un nombre arabe ou romain explicite à la fin du titre.
            # Note : on n'utilise que les chiffres arabes ou les romains ≥ 2 lettres
            # pour éviter les faux positifs avec la lettre "I" seule.
            bonus = 0.0
            try:
                # Chiffres arabes ou romains à 2+ lettres
                titre_suffix = re.search(
                    r"\b(ii|iii|iv|vi{0,3}|ix|x|\d+)\s*$", titre.lower()
                )
                if titre_suffix:
                    suf = titre_suffix.group(1)
                    suf_int = ROMAN_TO_INT.get(suf, int(suf) if suf.isdigit() else None)
                    if suf_int is not None and str(suf_int) == num_found:
                        bonus = 15.0
            except Exception:
                pass

            return base_score + bonus

        def check_url(url: str, num_found: str, separator: str) -> Optional[str]:
            nonlocal best_titre_url, best_titre_score
            if url in seen:
                return None
            seen.add(url)

            # Correspondance par titre (priorité si sous-série ou titre disponible)
            if titre:
                title_score = _title_score_for_url(url, num_found, separator)
                if title_score > best_titre_score:
                    best_titre_score = title_score
                    best_titre_url = url

            # Correspondance exacte par numéro (sauf si priorité au titre)
            if not use_title_priority and num_found == tome_str:
                return url

            return None

        # Stratégie d'extraction selon le type de série :
        #
        # - Série HS (arrière boutique, intégrale...) :
        #   1. Essai direct HS{tome} (ex: HS1 pour tome 1)
        #   2. Fallback par titre sur tous les albums HS
        #   3. Fallback par titre sur tous les albums Tome
        #
        # - Série "Avant la..." :
        #   1. Matching par titre sur tous les albums (Tome ET HS)
        #
        # - Série normale :
        #   1. Tome exact → retour immédiat
        #   2. Fallback par titre

        if is_hs_type:
            # Priorité : HS{num} exact
            hs_exact = None
            for m in pattern_hs.finditer(r.text):
                url, num = m.group(1), m.group(2)
                if url not in seen:
                    seen.add(url)
                    if num == tome_str:
                        hs_exact = url
                        break
            if hs_exact:
                return hs_exact

            # Sinon titre-matching sur les HS uniquement
            hs_seen: set = set()
            for m in pattern_hs.finditer(r.text):
                url, num = m.group(1), m.group(2)
                if url not in hs_seen:
                    hs_seen.add(url)
                    if titre:
                        sc = _title_score_for_url(url, num, "HS")
                        if sc > best_titre_score:
                            best_titre_score = sc
                            best_titre_url = url
            if best_titre_url and best_titre_score >= FUZZY_THRESHOLD:
                tqdm.write(f"  [Native] HS titre match (score={best_titre_score:.1f}): {best_titre_url}")
                return best_titre_url

            # Dernier recours : titre-matching sur les tomes normaux
            for m in pattern_tome.finditer(r.text):
                check_url(m.group(1), m.group(2), "Tome-")
            if best_titre_url and best_titre_score >= FUZZY_THRESHOLD:
                tqdm.write(f"  [Native] Tome titre match (score={best_titre_score:.1f}): {best_titre_url}")
                return best_titre_url

        else:
            # Pour les autres types (normal ou Avant la...)
            for m in pattern_tome.finditer(r.text):
                result_url = check_url(m.group(1), m.group(2), "Tome-")
                if result_url:  # Tome exact trouvé (pas use_title_priority)
                    return result_url

            for m in pattern_hs.finditer(r.text):
                check_url(m.group(1), m.group(2), "HS")

            # Meilleur titre match
            if best_titre_url and best_titre_score >= FUZZY_THRESHOLD:
                tqdm.write(
                    f"  [Native] Meilleur titre match (score={best_titre_score:.1f}): {best_titre_url}"
                )
                return best_titre_url

            # Dernier recours : tome exact même si use_title_priority
            if use_title_priority:
                for m in pattern_tome.finditer(r.text):
                    url, num = m.group(1), m.group(2)
                    if num == tome_str:
                        return url

    except Exception as e:
        tqdm.write(f"  [Native] Erreur: {e}")
    return None


# ─── 3. Scraping de la page album ─────────────────────────────────────────────

def _extract_li_values(li_element) -> tuple[str, list[str]]:
    """
    Extrait le texte d'une balise <label> et les valeurs (liens ou texte brut)
    d'un <li> de la section infos-albums.
    """
    from lxml import html as lxml_html

    label_els = li_element.xpath(".//label")
    label_txt = label_els[0].text_content().strip().rstrip(":").strip() if label_els else ""

    # Valeurs via les liens <a>
    link_texts = [
        a.text_content().strip()
        for a in li_element.xpath(".//a")
        if a.text_content().strip()
    ]
    if link_texts:
        return label_txt, link_texts

    # Valeur brute (texte du li sans le label)
    full_text = li_element.text_content().strip()
    if label_txt:
        raw_val = full_text.replace(label_els[0].text_content(), "").strip()
    else:
        raw_val = full_text
    # Nettoyage des espaces multiples
    raw_val = re.sub(r"\s+", " ", raw_val).strip()
    return label_txt, [raw_val] if raw_val else []


def _parse_year(depot_legal: str) -> str:
    """Extrait l'année depuis 'MM/YYYY' ou 'YYYY'."""
    m = re.search(r"(\d{4})", depot_legal)
    return m.group(1) if m else ""


async def scrape_bedetheque_page(url: str, client: httpx.AsyncClient) -> dict:
    """
    Scrape une page album Bédéthèque et retourne les métadonnées.
    """
    result = {
        "isbn": None,
        "titre": None,
        "serie": None,
        "tome": None,
        "collection": None,
        "scenariste": None,
        "dessinateur": None,
        "scenaristes": [],
        "dessinateurs": [],
        "couverture_url": None,
        "synopsis": None,
        "annee": None,
    }

    try:
        from lxml import html as lxml_html

        r = await client.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        if r.status_code != 200:
            tqdm.write(f"  [Scrape] HTTP {r.status_code} pour {url}")
            return result

        tree = lxml_html.fromstring(r.text)

        # ── Infos structurées (ul.infos-albums) ──
        mapping = {
            "Série": "serie",
            "Titre": "titre",
            "Tome": "tome",
            "Scénario": "_scenaristes",
            "Dessin": "_dessinateurs",
            "EAN/ISBN": "isbn",
            "Collection": "collection",
            "Dépot légal": "_depot",
            "Achev. impr.": "_depot_alt",
        }

        for li in tree.xpath('//ul[contains(@class,"infos-albums")]//li'):
            label_txt, values = _extract_li_values(li)
            key = mapping.get(label_txt)
            if not key or not values:
                continue

            if key == "isbn":
                # Nettoie l'ISBN (retire les tirets/espaces)
                result["isbn"] = re.sub(r"[^0-9X]", "", values[0])
            elif key in ("_scenaristes", "_dessinateurs"):
                real_key = key[1:]
                result[real_key] = values
            elif key == "_depot":
                if not result.get("annee"):
                    result["annee"] = _parse_year(values[0])
            elif key == "_depot_alt":
                if not result.get("annee"):
                    result["annee"] = _parse_year(values[0])
            else:
                result[key] = values[0]

        # ── Champs string consolidés ──
        if result["scenaristes"]:
            result["scenariste"] = ", ".join(result["scenaristes"])
        if result["dessinateurs"]:
            result["dessinateur"] = ", ".join(result["dessinateurs"])

        # ── Couverture ──
        covers = tree.xpath('//img[contains(@class,"image_album")]/@src')
        if covers:
            result["couverture_url"] = covers[0]

        # ── Synopsis ──
        synopsis_els = tree.xpath('//*[@itemprop="description"]')
        if synopsis_els:
            result["synopsis"] = synopsis_els[0].text_content().strip()

    except Exception as e:
        tqdm.write(f"  [Scrape] Erreur sur {url}: {e}")

    return result


# ─── 4. Résolution et enrichissement ──────────────────────────────────────────

def _score_url(url: str, titre: str, serie: str, tome: str) -> int:
    """
    Score de correspondance entre une URL Bédéthèque et les métadonnées d'un album.
    """
    # Extrait les tokens de l'URL
    url_lower = url.lower()
    slug = url_lower.split("/bd-")[-1] if "/bd-" in url_lower else url_lower

    # Score titre
    titre_score = fuzz.partial_ratio(titre.lower(), slug)
    # Score série
    serie_score = fuzz.partial_ratio(serie.lower().split()[0], slug)
    # Vérification du numéro de tome dans l'URL
    tome_in_url = f"-tome-{tome}-" in url_lower or f"-tome-{tome}." in url_lower
    tome_bonus = 30 if tome_in_url else 0

    return int((titre_score * 0.5 + serie_score * 0.3) + tome_bonus)


async def resolve_and_enrich(
    album: dict, cache: dict, client: httpx.AsyncClient
) -> dict:
    """
    Orchestre la recherche + scraping pour un album.
    """
    serie = album.get("serie", "").strip()
    tome = str(album.get("tome", "")).strip()
    titre = album.get("titre", "").strip()
    auteurs = album.get("auteurs", "").strip()

    enriched = dict(album)
    enriched.update(
        {
            "bedetheque_url": None,
            "needs_review": False,
            "source": None,
        }
    )

    # 1. Cache
    ck = cache_key(serie, tome)
    if ck in cache:
        cached = cache[ck]
        tqdm.write(f"  [Cache] {serie} T{tome}")
        enriched.update(cached)
        enriched["source"] = "cache"
        return enriched

    # 2. Brave Search (si clé disponible)
    bd_url = None
    source = None

    if BRAVE_API_KEY:
        tqdm.write(f"  [Brave] Recherche: {serie} T{tome}")
        bd_url = await brave_search_bedetheque(titre, tome, serie, client)
        if bd_url:
            score = _score_url(bd_url, titre, serie, tome)
            tqdm.write(f"  [Brave] URL trouvée (score={score}): {bd_url}")
            if score < FUZZY_THRESHOLD:
                tqdm.write(f"  [Brave] Score insuffisant ({score} < {FUZZY_THRESHOLD}), passage au fallback")
                bd_url = None
            else:
                source = "brave"

    # 3. Fallback natif
    if not bd_url:
        tqdm.write(f"  [Native] Recherche: {serie} T{tome}")
        bd_url = await bedetheque_native_search(serie, tome, client, titre=titre, auteurs=auteurs)
        if bd_url:
            # La fonction native fait déjà un scoring interne — on accepte son résultat
            tqdm.write(f"  [Native] URL trouvée: {bd_url}")
            source = "native"

    # 4. Scraping
    if bd_url:
        tqdm.write(f"  [Scrape] {bd_url}")
        scraped = await scrape_bedetheque_page(bd_url, client)
        enriched["bedetheque_url"] = bd_url
        enriched["source"] = source

        # Merge scraped data
        if scraped.get("isbn"):
            enriched["isbn"] = scraped["isbn"]
        if scraped.get("couverture_url"):
            enriched["cover_url"] = scraped["couverture_url"]
            # cover (chemin local) sera rempli après téléchargement dans main_async
        if scraped.get("synopsis"):
            enriched["synopsis"] = scraped["synopsis"]
        if scraped.get("annee"):
            enriched["annee"] = scraped["annee"]
        if scraped.get("collection"):
            enriched["collection"] = scraped["collection"]
        if scraped.get("scenariste"):
            enriched["scenariste"] = scraped["scenariste"]
        if scraped.get("dessinateur"):
            enriched["dessinateur"] = scraped["dessinateur"]
        if scraped.get("scenaristes"):
            enriched["scenaristes"] = scraped["scenaristes"]
        if scraped.get("dessinateurs"):
            enriched["dessinateurs"] = scraped["dessinateurs"]

        enriched["needs_review"] = False

        # Sauvegarde en cache
        cache_data = {
            "bedetheque_url": bd_url,
            "source": source,
            "isbn": enriched.get("isbn"),
            "cover_url": enriched.get("cover_url"),
            # cover (chemin local) mis à jour après téléchargement dans main_async
            "cover": enriched.get("cover", ""),
            "synopsis": enriched.get("synopsis"),
            "annee": enriched.get("annee"),
            "collection": enriched.get("collection"),
            "scenariste": enriched.get("scenariste"),
            "dessinateur": enriched.get("dessinateur"),
            "scenaristes": enriched.get("scenaristes", []),
            "dessinateurs": enriched.get("dessinateurs", []),
        }
        cache[ck] = cache_data

    else:
        tqdm.write(f"  [!] Aucune URL trouvée pour '{serie}' T{tome} — needs_review=True")
        enriched["needs_review"] = True
        enriched["source"] = None

    return enriched


# ─── 5. Main ──────────────────────────────────────────────────────────────────

async def main_async(input_file: str, output_file: str) -> None:
    # Chargement des données
    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    # Support deux formats : {"albums": [...]} ou [...]
    if isinstance(data, dict):
        albums = data.get("albums", [])
    elif isinstance(data, list):
        albums = data
    else:
        raise ValueError("Format JSON non reconnu")

    # Crée le dossier images si nécessaire
    Path(IMAGES_DIR).mkdir(parents=True, exist_ok=True)

    cache = load_cache(CACHE_FILE)
    results = []

    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=20,
    ) as client:
        bar = tqdm(albums, desc="Enrichissement", unit="album")
        for i, album in enumerate(bar):
            serie = album.get("serie", "?")
            tome = album.get("tome", "?")
            bar.set_postfix_str(f"{serie[:25]} T{tome}")

            from_cache = cache_key(serie, str(tome)) in cache
            enriched = await resolve_and_enrich(album, cache, client)

            # Téléchargement de la couverture
            cover_url = enriched.get("cover_url")
            if cover_url:
                tqdm.write(f"  [Cover] Téléchargement: {cover_url}")
                local_path = await download_cover(
                    cover_url, serie, str(tome), client
                )
                if local_path:
                    enriched["cover"] = local_path
                    # Met à jour le cache avec le chemin local
                    ck = cache_key(serie, str(tome))
                    if ck in cache:
                        cache[ck]["cover"] = local_path

            results.append(enriched)

            # Sauvegarde cache après chaque album (résistance aux interruptions)
            save_cache(cache, CACHE_FILE)

            # Pause aléatoire uniquement si on a fait une vraie requête Bédéthèque
            if i < len(albums) - 1 and not from_cache:
                delay = random.uniform(15, 35)
                tqdm.write(f"  [Sleep] Pause {delay:.1f}s…")
                await asyncio.sleep(delay)

    # Sauvegarde des résultats
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    tqdm.write(f"\nTerminé. {len(results)} albums écrits dans '{output_file}'")

    # Statistiques
    found = sum(1 for a in results if not a.get("needs_review"))
    covers = sum(1 for a in results if a.get("cover") and a["cover"].startswith(IMAGES_DIR))
    not_found = len(results) - found
    tqdm.write(f"  Trouvés    : {found}")
    tqdm.write(f"  Couvertures: {covers}")
    tqdm.write(f"  À réviser  : {not_found}")


def main(input_file: str, output_file: str) -> None:
    asyncio.run(main_async(input_file, output_file))


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enrichit les albums BD avec les métadonnées de Bédéthèque"
    )
    parser.add_argument(
        "--input",
        default="albums_input.json",
        help="Fichier JSON d'entrée (défaut: albums_input.json)",
    )
    parser.add_argument(
        "--output",
        default="albums_output.json",
        help="Fichier JSON de sortie (défaut: albums_output.json)",
    )
    args = parser.parse_args()
    main(args.input, args.output)
