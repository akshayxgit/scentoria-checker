# Scentoria Tester Availability Checker

Checks tester variant availability across all products on [scentoria.co.in](https://scentoria.co.in/collections/testers) using the Shopify JSON API. Includes a Streamlit dashboard for browsing and filtering results.

## Requirements

- Python 3.10+

## Setup

```bash
git clone https://github.com/akshayxgit/scentoria-checker.git
cd scentoria-checker
pip install -r requirements.txt
```

## Usage

### 1. Fetch latest data

```bash
python3 tester_checker.py
```

This scrapes all products from the testers collection and exports results to `tester_availability.csv`.

### 2. (Optional) Fetch Fragrantica ratings

```bash
python3 fragrantica_ratings.py
```

This looks up each available tester on Fragrantica and adds rating + review count to the CSV. Results are cached in `fragrantica_cache.json` so subsequent runs only fetch new products.

**Note:** This step is slow (~7 seconds per product due to rate limiting). It's resumable — if interrupted, re-run and it picks up where it left off. Will not work on networks that block fragrantica.com.

### 3. Launch the dashboard

```bash
streamlit run dashboard.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

## Dashboard Features

- Filter by availability status (Available / Sold Out)
- Search by product name
- Hide partial testers
- Filter by price range
- Sort by name, price, status, or Fragrantica rating
- Clickable links to product pages and Fragrantica pages

## How It Works

- Fetches product data from Shopify's `/collections/testers/products.json` endpoint
- Extracts variant-level availability (tester variants are identified by "tester" in the variant title)
- No browser automation or Selenium needed — pure API calls
- Concurrent page fetching for speed (~8 seconds for 4000+ products)
