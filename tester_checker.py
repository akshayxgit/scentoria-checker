"""
Scentoria Tester Availability Checker

Uses Shopify's collection products JSON API to check tester variant
availability. The collection endpoint returns full product + variant data,
so we only need to paginate through that one endpoint.

Fetches pages concurrently for speed. Exports results to tester_availability.csv.
"""

import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE_URL = "https://scentoria.co.in"
COLLECTION_JSON_URL = f"{BASE_URL}/collections/testers/products.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

PRODUCTS_PER_PAGE = 250
MAX_RETRIES = 5
RETRY_BACKOFF = 3  # seconds, multiplied by attempt number
CONCURRENT_WORKERS = 6  # parallel page fetches


def request_with_retry(url, params=None):
    """GET request with retry and exponential backoff on 429."""
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return resp
        if resp.status_code == 429:
            wait = RETRY_BACKOFF * attempt
            print(f"    Rate limited (429). Waiting {wait}s ... (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
        else:
            resp.raise_for_status()
    resp.raise_for_status()
    return resp


def _fetch_page(page: int) -> tuple[int, list[dict]]:
    """Fetch a single collection page. Returns (page_number, products)."""
    params = {"limit": str(PRODUCTS_PER_PAGE)}
    if page > 1:
        params["page"] = str(page)
    resp = request_with_retry(COLLECTION_JSON_URL, params=params)
    products = resp.json().get("products", [])
    return page, products


def fetch_all_products() -> list[dict]:
    """Fetch all products using concurrent batches — stops when done."""

    # Fetch page 1 first
    print("  Fetching page 1...")
    _, first_page = _fetch_page(1)
    if not first_page:
        return []

    print(f"    Page 1: {len(first_page)} products")
    if len(first_page) < PRODUCTS_PER_PAGE:
        print(f"\nFetched {len(first_page)} products total.\n")
        return first_page

    # Fetch remaining pages in concurrent batches until we hit an empty page
    all_products = list(first_page)
    batch_start = 2

    while True:
        batch_pages = list(range(batch_start, batch_start + CONCURRENT_WORKERS))
        print(f"  Fetching pages {batch_pages[0]}-{batch_pages[-1]} concurrently...")

        batch_results: dict[int, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as pool:
            futures = {pool.submit(_fetch_page, p): p for p in batch_pages}
            for future in as_completed(futures):
                page_num, products = future.result()
                batch_results[page_num] = products

        # Append in order; stop at first incomplete/empty page
        done = False
        for p in sorted(batch_results.keys()):
            prods = batch_results[p]
            if not prods:
                done = True
                break
            all_products.extend(prods)
            print(f"    Page {p}: {len(prods)} products")
            if len(prods) < PRODUCTS_PER_PAGE:
                done = True
                break

        if done:
            break
        batch_start += CONCURRENT_WORKERS

    print(f"\nFetched {len(all_products)} products total.\n")
    return all_products


def analyze_product(product: dict) -> dict:
    """Analyze a single product dict for tester variant availability."""
    title = product.get("title", "Unknown")
    handle = product.get("handle", "Unknown")
    product_url = f"{BASE_URL}/products/{handle}"
    variants = product.get("variants", [])

    tester_variants = []
    for v in variants:
        variant_title = v.get("title", "").lower()
        if "tester" in variant_title:
            tester_variants.append({
                "variant_title": v.get("title", ""),
                "available": v.get("available", False),
                "price": v.get("price", "N/A"),
                "variant_id": v.get("id", ""),
            })

    has_tester = len(tester_variants) > 0
    tester_available = any(tv["available"] for tv in tester_variants)

    return {
        "title": title,
        "handle": handle,
        "url": product_url,
        "has_tester_variant": has_tester,
        "tester_available": tester_available,
        "tester_variants": tester_variants,
    }


def export_csv(results: list[dict], filename: str = "tester_availability.csv"):
    """Export results to a CSV file."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Product Title",
            "Handle",
            "URL",
            "Has Tester Variant",
            "Tester Available",
            "Tester Variant Details",
        ])
        for r in results:
            details = "; ".join(
                f"{tv['variant_title']} (Rs.{tv['price']}) - "
                f"{'AVAILABLE' if tv['available'] else 'SOLD OUT'}"
                for tv in r["tester_variants"]
            )
            writer.writerow([
                r["title"],
                r["handle"],
                r["url"],
                r["has_tester_variant"],
                r["tester_available"],
                details,
            ])
    print(f"\nResults exported to {filename}")


def print_summary(results: list[dict]):
    """Print a summary to the terminal."""
    available = [r for r in results if r["tester_available"]]
    unavailable = [r for r in results if r["has_tester_variant"] and not r["tester_available"]]
    no_tester = [r for r in results if not r["has_tester_variant"]]

    print("=" * 70)
    print("  TESTER AVAILABILITY REPORT")
    print(f"  Total products scanned: {len(results)}")
    print("=" * 70)

    print(f"\nTESTER AVAILABLE ({len(available)}):")
    print("-" * 50)
    for r in sorted(available, key=lambda x: x["title"]):
        print(f"  {r['title']}")
        for tv in r["tester_variants"]:
            if tv["available"]:
                print(f"    -> {tv['variant_title']} -- Rs.{tv['price']}")

    print(f"\nTESTER SOLD OUT ({len(unavailable)}):")
    print("-" * 50)
    for r in sorted(unavailable, key=lambda x: x["title"]):
        print(f"  {r['title']}")
        for tv in r["tester_variants"]:
            print(f"    -> {tv['variant_title']} -- Rs.{tv['price']} (SOLD OUT)")

    if no_tester:
        print(f"\nNO TESTER VARIANT FOUND ({len(no_tester)}):")
        print("-" * 50)
        for r in sorted(no_tester, key=lambda x: x["title"]):
            print(f"  {r['title']}")

    print()
    print("=" * 70)
    print(f"  Summary: {len(available)} available | {len(unavailable)} sold out | {len(no_tester)} no tester variant")
    print("=" * 70)


def main():
    print("Scentoria Tester Availability Checker")
    print("=" * 40)
    print()

    # Step 1: Fetch all products from collection JSON API
    products = fetch_all_products()

    if not products:
        print("No products found. Exiting.")
        sys.exit(1)

    # Step 2: Analyze each product for tester variants
    print("Analyzing tester variant availability...")
    results = [analyze_product(p) for p in products]
    print(f"Analyzed {len(results)} products.\n")

    # Step 3: Print summary
    print_summary(results)

    # Step 4: Export to CSV
    export_csv(results)


if __name__ == "__main__":
    main()
