"""
Sample business database ("Demo - Sales") so ABIET can be tried without
connecting a real database. Generated deterministically on first use.
"""

from __future__ import annotations

import random
import sqlite3
import threading
from datetime import date, timedelta
from pathlib import Path

from backend.config import settings

DEMO_FILE_NAME = "demo_sales.sqlite"
DEMO_VERSION = 1
_lock = threading.Lock()

REGIONS = [
    ("North America", ["New York", "Chicago", "Toronto", "Austin", "Seattle", "Denver"]),
    ("Europe", ["London", "Berlin", "Paris", "Madrid", "Amsterdam", "Milan"]),
    ("Asia Pacific", ["Singapore", "Tokyo", "Sydney", "Mumbai", "Seoul"]),
    ("Middle East & Africa", ["Dubai", "Riyadh", "Cairo", "Johannesburg", "Lagos"]),
    ("Latin America", ["Sao Paulo", "Mexico City", "Bogota", "Buenos Aires", "Lima"]),
]
COUNTRIES = {
    "New York": "USA", "Chicago": "USA", "Austin": "USA", "Seattle": "USA", "Denver": "USA",
    "Toronto": "Canada", "London": "UK", "Berlin": "Germany", "Paris": "France", "Madrid": "Spain",
    "Amsterdam": "Netherlands", "Milan": "Italy", "Singapore": "Singapore", "Tokyo": "Japan",
    "Sydney": "Australia", "Mumbai": "India", "Seoul": "South Korea", "Dubai": "UAE",
    "Riyadh": "Saudi Arabia", "Cairo": "Egypt", "Johannesburg": "South Africa", "Lagos": "Nigeria",
    "Sao Paulo": "Brazil", "Mexico City": "Mexico", "Bogota": "Colombia", "Buenos Aires": "Argentina",
    "Lima": "Peru",
}  # fmt: skip
CATEGORIES = {
    "Laptops": [("UltraBook 14", 1299), ("ProBook 16", 1899), ("StudentBook 13", 649), ("WorkStation X", 2499)],
    "Monitors": [("ClearView 24", 219), ("ClearView 27 4K", 449), ("CurveMax 34", 699)],
    "Accessories": [("Wireless Mouse", 29), ("Mechanical Keyboard", 99), ("USB-C Dock", 189), ("Laptop Sleeve", 39),
                    ("Noise-Cancelling Headset", 179), ("HD Webcam", 79)],
    "Software": [("Office Suite (1 yr)", 99), ("Security Pro (1 yr)", 59), ("Design Studio (1 yr)", 299),
                 ("Cloud Backup 1TB (1 yr)", 119)],
    "Services": [("On-site Setup", 150), ("Extended Warranty 2 yr", 199), ("Data Migration", 350)],
    "Networking": [("Mesh Router Kit", 329), ("Gigabit Switch 24p", 259), ("Wi-Fi 7 Access Point", 229)],
}  # fmt: skip
FIRST = [
    "Aisha",
    "Ben",
    "Carlos",
    "Diana",
    "Ethan",
    "Fatima",
    "George",
    "Hana",
    "Ivan",
    "Julia",
    "Kenji",
    "Lina",
    "Marco",
    "Nadia",
    "Omar",
    "Priya",
    "Quinn",
    "Rosa",
    "Sam",
    "Tariq",
    "Uma",
    "Victor",
    "Wei",
    "Yara",
    "Zane",
]
LAST = [
    "Khan",
    "Smith",
    "Garcia",
    "Muller",
    "Rossi",
    "Tanaka",
    "Okafor",
    "Silva",
    "Novak",
    "Haddad",
    "Kim",
    "Patel",
    "Johnson",
    "Dubois",
    "Ivanova",
    "Lopez",
    "Chen",
    "Hughes",
    "Nakamura",
    "Andersen",
]
COMPANY_WORDS = [
    "Apex",
    "Blue",
    "Cedar",
    "Delta",
    "Evergreen",
    "Falcon",
    "Granite",
    "Harbor",
    "Iris",
    "Juniper",
    "Keystone",
    "Lumen",
    "Maple",
    "Nova",
    "Orbit",
    "Pioneer",
    "Quantum",
    "Summit",
    "Terra",
    "Vertex",
]
COMPANY_SUFFIX = ["Labs", "Logistics", "Health", "Retail", "Capital", "Studios", "Foods", "Energy", "Systems", "Group"]
SEGMENTS = ["Enterprise", "SMB", "Consumer", "Government"]
CHANNELS = ["Online", "Partner", "Direct Sales"]
NUM_CUSTOMERS = 180  # must not exceed len(COMPANY_WORDS) * len(COMPANY_SUFFIX)
START = date(2024, 7, 1)
END = date(2026, 6, 30)

SCHEMA = """
CREATE TABLE regions (
    region_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    job_title TEXT NOT NULL,
    region_id INTEGER NOT NULL REFERENCES regions(region_id),
    hire_date DATE NOT NULL,
    annual_quota NUMERIC(12,2) NOT NULL
);
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    company_name TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    segment TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    region_id INTEGER NOT NULL REFERENCES regions(region_id),
    account_manager_id INTEGER REFERENCES employees(employee_id),
    signup_date DATE NOT NULL
);
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    list_price NUMERIC(10,2) NOT NULL,
    unit_cost NUMERIC(10,2) NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    employee_id INTEGER REFERENCES employees(employee_id),
    order_date DATE NOT NULL,
    status TEXT NOT NULL,
    channel TEXT NOT NULL,
    shipped_date DATE
);
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL,
    discount NUMERIC(4,2) NOT NULL DEFAULT 0
);
CREATE INDEX ix_orders_customer ON orders(customer_id);
CREATE INDEX ix_orders_date ON orders(order_date);
CREATE INDEX ix_items_order ON order_items(order_id);
CREATE INDEX ix_items_product ON order_items(product_id);
CREATE VIEW order_revenue AS
SELECT o.order_id, o.order_date, o.customer_id, o.status,
       ROUND(SUM(i.quantity * i.unit_price * (1 - i.discount)), 2) AS revenue
FROM orders o JOIN order_items i ON i.order_id = o.order_id
GROUP BY o.order_id, o.order_date, o.customer_id, o.status;
"""


def demo_path() -> Path:
    return settings.sqlite_dir / DEMO_FILE_NAME


def _build(path: Path) -> None:
    rng = random.Random(42)
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        db.executescript(SCHEMA)

        region_rows = [(i + 1, name) for i, (name, _) in enumerate(REGIONS)]
        db.executemany("INSERT INTO regions VALUES (?, ?)", region_rows)

        employees = []
        eid = 0
        for region_id, (_, _cities) in enumerate(REGIONS, start=1):
            eid += 1
            employees.append(
                (
                    eid,
                    rng.choice(FIRST),
                    rng.choice(LAST),
                    "Regional Sales Manager",
                    region_id,
                    (date(2019, 1, 1) + timedelta(days=rng.randint(0, 1500))).isoformat(),
                    2_000_000,
                )
            )
            for _ in range(rng.randint(2, 3)):
                eid += 1
                employees.append(
                    (
                        eid,
                        rng.choice(FIRST),
                        rng.choice(LAST),
                        "Account Executive",
                        region_id,
                        (date(2020, 1, 1) + timedelta(days=rng.randint(0, 1800))).isoformat(),
                        rng.choice([600_000, 750_000, 900_000]),
                    )
                )
        db.executemany("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?)", employees)
        reps_by_region: dict[int, list[int]] = {}
        for e in employees:
            if e[3] == "Account Executive":
                reps_by_region.setdefault(e[4], []).append(e[0])

        customers = []
        company_names = [f"{word} {suffix}" for word in COMPANY_WORDS for suffix in COMPANY_SUFFIX]
        rng.shuffle(company_names)
        for cid, company in enumerate(company_names[:NUM_CUSTOMERS], start=1):
            region_id = rng.choices(range(1, 6), weights=[34, 28, 18, 10, 10])[0]
            city = rng.choice(REGIONS[region_id - 1][1])
            first, last = rng.choice(FIRST), rng.choice(LAST)
            domain = company.lower().replace(" ", "") + ".example"
            customers.append(
                (
                    cid,
                    company,
                    f"{first} {last}",
                    f"{first.lower()}.{last.lower()}@{domain}",
                    rng.choices(SEGMENTS, weights=[25, 40, 25, 10])[0],
                    city,
                    COUNTRIES[city],
                    region_id,
                    rng.choice(reps_by_region[region_id]),
                    (date(2022, 1, 1) + timedelta(days=rng.randint(0, 1000))).isoformat(),
                )
            )
        db.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", customers)

        products = []
        pid = 0
        for cat_id, (cat, items) in enumerate(CATEGORIES.items(), start=1):
            db.execute("INSERT INTO categories VALUES (?, ?)", (cat_id, cat))
            for name, price in items:
                pid += 1
                margin = rng.uniform(0.25, 0.6) if cat in ("Software", "Services") else rng.uniform(0.12, 0.35)
                products.append((pid, name, cat_id, price, round(price * (1 - margin), 2), 0 if pid == 3 else 1))
        db.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)", products)

        # Cheaper products sell more often.
        popularity = [1.0 / (p[3] ** 0.5) for p in products]
        orders, items = [], []
        oid = iid = 0
        total_days = (END - START).days
        for _ in range(2600):
            oid += 1
            day = START + timedelta(days=int(total_days * (rng.random() ** 0.8)))
            if day.month in (11, 12) and rng.random() < 0.35:
                day = day - timedelta(days=rng.randint(0, 20))
            cust = customers[rng.randint(0, len(customers) - 1)]
            status = rng.choices(
                ["Delivered", "Shipped", "Processing", "Cancelled", "Returned"], weights=[70, 10, 6, 9, 5]
            )[0]
            if day > END - timedelta(days=20) and status == "Delivered":
                status = rng.choice(["Shipped", "Processing"])
            shipped = None
            if status in ("Delivered", "Shipped", "Returned"):
                shipped = (day + timedelta(days=rng.randint(1, 7))).isoformat()
            orders.append(
                (
                    oid,
                    cust[0],
                    cust[8] if rng.random() < 0.8 else None,
                    day.isoformat(),
                    status,
                    rng.choices(CHANNELS, weights=[50, 25, 25])[0],
                    shipped,
                )
            )
            line_count = rng.choices([1, 2, 3, 4], weights=[40, 30, 20, 10])[0]
            picked = set(rng.choices(range(1, len(products) + 1), weights=popularity, k=line_count))
            for prod_id in sorted(picked):
                iid += 1
                qty = rng.randint(1, 3) if cust[4] == "Consumer" else rng.randint(1, 20)
                if cust[4] == "Enterprise":
                    qty += rng.randint(0, 30)
                discount = rng.choice([0, 0, 0, 0.05, 0.1, 0.15]) if qty >= 5 else 0
                items.append((iid, oid, prod_id, qty, products[prod_id - 1][3], discount))
        db.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", orders)
        db.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)", items)
        db.execute(f"PRAGMA user_version = {DEMO_VERSION}")
        db.commit()
    finally:
        db.close()
    tmp.replace(path)


def ensure_demo_database() -> Path:
    """Create the demo database if it does not exist (or is outdated) and return its path."""
    path = demo_path()
    with _lock:
        if path.exists():
            with sqlite3.connect(path) as db:
                if db.execute("PRAGMA user_version").fetchone()[0] == DEMO_VERSION:
                    return path
        path.parent.mkdir(parents=True, exist_ok=True)
        _build(path)
    return path
