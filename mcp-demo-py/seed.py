import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "demo.db"

SCHEMA = """
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    city   TEXT NOT NULL,
    joined TEXT NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    amount      REAL NOT NULL,
    created_at  TEXT NOT NULL
);
"""

CUSTOMERS = [
    (1, "张伟", "武汉", "2024-03-11"),
    (2, "李娜", "上海", "2024-07-02"),
    (3, "王强", "武汉", "2025-01-19"),
    (4, "赵敏", "北京", "2025-05-30"),
]

ORDERS = [
    (1, 1, 128.50, "2026-08-03"),
    (2, 1, 340.00, "2026-08-19"),
    (3, 2,  99.90, "2026-09-01"),
    (4, 3, 520.00, "2026-09-12"),
    (5, 4,  75.20, "2026-09-28"),
    (6, 2, 210.00, "2026-10-02"),
]


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", CUSTOMERS)
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", ORDERS)
    conn.commit()
    conn.close()
    print(f"已生成 {DB_PATH}")


if __name__ == "__main__":
    main()