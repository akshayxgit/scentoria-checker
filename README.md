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

### 2. Launch the dashboard

```bash
streamlit run dashboard.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

## Dashboard Features

- Filter by availability status (Available / Sold Out)
- Search by product name
- Hide partial testers
- Filter by price range
- Sort by name, price, or status
- Clickable links to product pages

## How It Works

- Fetches product data from Shopify's `/collections/testers/products.json` endpoint
- Extracts variant-level availability (tester variants are identified by "tester" in the variant title)
- No browser automation or Selenium needed — pure API calls
- Concurrent page fetching for speed (~8 seconds for 4000+ products)
