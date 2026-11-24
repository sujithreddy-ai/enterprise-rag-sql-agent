import sqlite3
import random

conn = sqlite3.connect("sample_data/sales_metrics.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS sales_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region TEXT,
    quarter TEXT,
    product_tier TEXT,
    revenue_inr REAL,
    churned_accounts INTEGER
)
""")

regions = ["South", "West", "North", "East"]
quarters = ["Q1-2026", "Q2-2026", "Q3-2026"]
tiers = ["Starter", "Growth", "Enterprise"]

rows = []
for _ in range(300):
    reg = random.choice(regions)
    qtr = random.choice(quarters)
    tier = random.choice(tiers)
    rev = round(random.uniform(50000, 450000), 2)
    churn = random.randint(0, 8)
    rows.append((reg, qtr, tier, rev, churn))

cur.executemany(
    "INSERT INTO sales_metrics (region, quarter, product_tier, revenue_inr, churned_accounts) VALUES (?, ?, ?, ?, ?)",
    rows
)
conn.commit()
conn.close()
print("Created sample_data/sales_metrics.db with 300 rows.")
