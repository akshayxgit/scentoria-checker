import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Scentoria Tester Dashboard", layout="wide")

st.title("Scentoria Tester Availability Dashboard")


@st.cache_data(ttl=300)
def load_data():
    df = pd.read_csv("tester_availability.csv")
    # Parse price from Tester Variant Details
    def extract_min_price(details):
        if pd.isna(details) or not details:
            return None
        prices = re.findall(r"Rs\.([\d.]+)", details)
        if prices:
            return min(float(p) for p in prices)
        return None

    df["Min Price"] = df["Tester Variant Details"].apply(extract_min_price)
    return df


df = load_data()

# --- Metrics row ---
total = len(df)
available = df["Tester Available"].sum()
sold_out = total - available

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Products", total)
col2.metric("Testers Available", int(available))
col3.metric("Sold Out", int(sold_out))

has_ratings = "Fragrantica Rating" in df.columns and df["Fragrantica Rating"].notna().any()
if has_ratings:
    rated_count = df["Fragrantica Rating"].notna().sum()
    col4.metric("With Ratings", int(rated_count))
else:
    col4.metric("With Ratings", "N/A")

st.divider()

# --- Filters ---
col_filter, col_search, col_partial = st.columns([1, 2, 1])

with col_filter:
    status_filter = st.radio(
        "Filter by status",
        ["All", "Available", "Sold Out"],
        horizontal=True,
    )

with col_search:
    search = st.text_input("Search product name", placeholder="e.g. Sauvage, Oud, Santal...")

with col_partial:
    hide_partials = st.checkbox("Hide Partials", value=False)

filtered = df.copy()

if hide_partials:
    filtered = filtered[~filtered["Product Title"].str.contains("partial", case=False, na=False)]

if status_filter == "Available":
    filtered = filtered[filtered["Tester Available"] == True]
elif status_filter == "Sold Out":
    filtered = filtered[filtered["Tester Available"] == False]

if search:
    filtered = filtered[filtered["Product Title"].str.contains(search, case=False, na=False)]

# --- Price range filter ---
if filtered["Min Price"].notna().any():
    min_p = float(filtered["Min Price"].min())
    max_p = float(filtered["Min Price"].max())
    if min_p < max_p:
        price_range = st.slider(
            "Price range (Rs.)",
            min_value=min_p,
            max_value=max_p,
            value=(min_p, max_p),
            step=100.0,
        )
        filtered = filtered[
            (filtered["Min Price"] >= price_range[0])
            & (filtered["Min Price"] <= price_range[1])
        ]

st.caption(f"Showing {len(filtered)} of {total} products")

# --- Sort control ---
sort_col, sort_dir = st.columns([2, 1])
sort_options = ["Product Title", "Tester Price (lowest)", "Status"]
if has_ratings:
    sort_options.append("Fragrantica Rating")
with sort_col:
    sort_by = st.selectbox("Sort by", sort_options)
with sort_dir:
    sort_order = st.radio("Order", ["Ascending", "Descending"], horizontal=True)

ascending = sort_order == "Ascending"

# --- Results table ---
cols = ["Product Title", "Brand", "Tester Available", "Min Price", "Tester Variant Details", "URL"]
if has_ratings:
    cols.extend(["Fragrantica Rating", "Fragrantica Votes", "Fragrantica URL"])
# Only use columns that exist
cols = [c for c in cols if c in filtered.columns]
display_df = filtered[cols].copy()
display_df["Tester Available"] = display_df["Tester Available"].map({True: "Available", False: "Sold Out"})
rename_map = {
    "Tester Available": "Status",
    "Min Price": "Tester Price (lowest)",
    "Tester Variant Details": "Variants",
}
if has_ratings:
    rename_map["Fragrantica Rating"] = "Fragrantica Rating"
    rename_map["Fragrantica Votes"] = "Fragrantica Votes"
    rename_map["Fragrantica URL"] = "Fragrantica URL"
display_df = display_df.rename(columns=rename_map)

sort_map = {"Product Title": "Product Title", "Tester Price (lowest)": "Tester Price (lowest)", "Status": "Status"}
display_df = display_df.sort_values(sort_map[sort_by], ascending=ascending, na_position="last")

column_config = {
    "URL": st.column_config.LinkColumn("Link", display_text="Open"),
}
if has_ratings and "Fragrantica URL" in display_df.columns:
    column_config["Fragrantica URL"] = st.column_config.LinkColumn("Fragrantica", display_text="Open")
    column_config["Fragrantica Rating"] = st.column_config.NumberColumn("Rating", format="%.1f")

st.dataframe(
    display_df,
    column_config=column_config,
    width="stretch",
    hide_index=True,
    height=600,
)

# --- Chart ---
st.subheader("Availability breakdown")
chart_data = pd.DataFrame({
    "Status": ["Available", "Sold Out"],
    "Count": [int(available), int(sold_out)],
})
st.bar_chart(chart_data, x="Status", y="Count", color="Status")
