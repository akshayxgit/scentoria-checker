"""
Fragrantica Rating Fetcher

Reads tester_availability.csv, looks up each available tester on Fragrantica,
and adds rating + review count. Results are cached to avoid re-fetching.

Uses:
  1. Fragrantica search page to find the perfume URL
  2. Fragrantica product page to extract rating data from JSON-LD

Run after tester_checker.py:
    python3 fragrantica_ratings.py
"""

import csv
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

CACHE_FILE = "fragrantica_cache.json"
INPUT_CSV = "tester_availability.csv"
OUTPUT_CSV = "tester_availability.csv"  # overwrites with enriched data
REQUEST_DELAY = 4  # seconds between Fragrantica requests
SEARCH_DELAY = 3   # seconds between search requests
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Words to strip from product title before searching
STRIP_WORDS = [
    "partial", "edp", "edt", "parfum", "extrait de parfum",
    "eau de parfum", "eau de toilette", "cologne", "attar",
    "w/o cap", "w/o box", "no cap", "no box", "with cap", "with box",
]


def load_cache() -> dict:
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def clean_product_name(title: str) -> str:
    """Strip concentration/format suffixes to get the core fragrance name."""
    name = title.strip()
    for word in STRIP_WORDS:
        name = re.sub(rf"\b{re.escape(word)}\b", "", name, flags=re.IGNORECASE)
    # Remove extra whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def make_cache_key(title: str, brand: str) -> str:
    """Normalize into a cache key."""
    return f"{brand.lower().strip()}::{clean_product_name(title).lower()}"


def _get(url, params=None):
    """GET with retry on transient errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429:
                wait = 10 * attempt
                print(f"    Rate limited. Waiting {wait}s (attempt {attempt})")
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                print(f"    Blocked (403). Skipping.")
                return None
            resp.raise_for_status()
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                print(f"    Request failed: {e}")
                return None
            time.sleep(5 * attempt)
    return None


def search_fragrantica(name: str, brand: str) -> str | None:
    """Search Fragrantica for a perfume and return the URL."""
    query = f"{name} {brand}".strip()
    url = "https://www.fragrantica.com/search/"
    resp = _get(url, params={"query": query})
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Look for perfume links in search results
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/perfume/" in href and href.endswith(".html"):
            if not href.startswith("http"):
                href = f"https://www.fragrantica.com{href}"
            return href

    return None


def fetch_rating(url: str) -> dict:
    """Fetch rating from a Fragrantica product page."""
    resp = _get(url)
    if not resp:
        return {"rating": None, "votes": None, "fragrantica_url": url}

    soup = BeautifulSoup(resp.text, "lxml")

    rating = None
    votes = None

    # Method 1: JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0]
            agg = data.get("aggregateRating", {})
            if agg:
                rating = float(agg.get("ratingValue", 0)) or None
                votes = int(agg.get("ratingCount", 0)) or None
                if rating:
                    break
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    # Method 2: itemprop attributes
    if not rating:
        rv = soup.find(itemprop="ratingValue")
        rc = soup.find(itemprop="ratingCount")
        if rv:
            try:
                rating = float(rv.text.strip())
            except ValueError:
                pass
        if rc:
            try:
                votes = int(rc.text.strip().replace(",", ""))
            except ValueError:
                pass

    # Method 3: Look for rating in specific spans/divs
    if not rating:
        for span in soup.find_all("span"):
            text = span.text.strip()
            match = re.match(r"^(\d\.\d{1,2})\s*$", text)
            if match:
                val = float(match.group(1))
                if 1.0 <= val <= 5.0:
                    rating = val
                    break

    return {
        "rating": rating,
        "votes": votes,
        "fragrantica_url": url,
    }


def read_csv() -> list[dict]:
    """Read the tester availability CSV."""
    rows = []
    with open(INPUT_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def write_csv(rows: list[dict]):
    """Write enriched CSV."""
    fieldnames = [
        "Product Title", "Handle", "Brand", "URL",
        "Has Tester Variant", "Tester Available", "Tester Variant Details",
        "Fragrantica Rating", "Fragrantica Votes", "Fragrantica URL",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nEnriched CSV written to {OUTPUT_CSV}")


def main():
    print("Fragrantica Rating Fetcher")
    print("=" * 40)

    rows = read_csv()
    if not rows:
        print("No data in CSV. Run tester_checker.py first.")
        sys.exit(1)

    # Only fetch ratings for available testers
    available_rows = [r for r in rows if r.get("Tester Available") == "True"]
    print(f"Total products: {len(rows)}")
    print(f"Available testers to look up: {len(available_rows)}")

    cache = load_cache()
    print(f"Cache entries: {len(cache)}\n")

    # Deduplicate by cleaned name + brand to avoid redundant lookups
    # e.g., "Sauvage EDP" and "Sauvage EDP Partial" → same fragrance
    lookup_map: dict[str, dict] = {}  # cache_key → rating data
    products_to_search: list[tuple[str, str, str]] = []  # (cache_key, clean_name, brand)

    for row in available_rows:
        title = row.get("Product Title", "")
        brand = row.get("Brand", "")
        key = make_cache_key(title, brand)

        if key in cache:
            lookup_map[key] = cache[key]
        elif key not in {p[0] for p in products_to_search}:
            clean = clean_product_name(title)
            products_to_search.append((key, clean, brand))

    print(f"Already cached: {len(lookup_map)}")
    print(f"Need to fetch: {len(products_to_search)}")

    if products_to_search:
        print(f"\nFetching ratings (with {REQUEST_DELAY}s delay between requests)...")
        print(f"Estimated time: ~{len(products_to_search) * (REQUEST_DELAY + SEARCH_DELAY) // 60} minutes\n")

    for i, (key, clean_name, brand) in enumerate(products_to_search, 1):
        print(f"  [{i}/{len(products_to_search)}] {brand} - {clean_name}")

        # Step 1: Find Fragrantica URL
        frag_url = search_fragrantica(clean_name, brand)
        time.sleep(SEARCH_DELAY)

        if not frag_url:
            print(f"    Not found on Fragrantica")
            result = {"rating": None, "votes": None, "fragrantica_url": None}
        else:
            print(f"    Found: {frag_url}")
            # Step 2: Fetch rating
            result = fetch_rating(frag_url)
            time.sleep(REQUEST_DELAY)

            if result["rating"]:
                print(f"    Rating: {result['rating']} ({result['votes']} votes)")
            else:
                print(f"    Could not extract rating")

        cache[key] = result
        lookup_map[key] = result

        # Save cache after each fetch (resumable)
        if i % 10 == 0:
            save_cache(cache)

    # Final cache save
    save_cache(cache)

    # Enrich all rows
    for row in rows:
        title = row.get("Product Title", "")
        brand = row.get("Brand", "")
        key = make_cache_key(title, brand)
        data = lookup_map.get(key, {})

        row["Fragrantica Rating"] = data.get("rating", "")
        row["Fragrantica Votes"] = data.get("votes", "")
        row["Fragrantica URL"] = data.get("fragrantica_url", "")

    write_csv(rows)

    # Print summary
    rated = sum(1 for r in rows if r.get("Fragrantica Rating"))
    print(f"\nProducts with ratings: {rated}")
    print(f"Products without ratings: {len(rows) - rated}")


if __name__ == "__main__":
    main()
