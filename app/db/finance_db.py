import os
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("griffsox.finance_db")

# DB_PATH is configurable via FINANCE_DB_PATH env var (for persistent volume on AWS)
# Falls back to <project_root>/data/finance_records.db
_default_db_dir = Path(__file__).resolve().parent.parent.parent / "data"
_env_db_path = os.environ.get("FINANCE_DB_PATH", "")
DB_PATH = _env_db_path if _env_db_path else str(_default_db_dir / "finance_records.db")
DB_DIR = os.path.dirname(DB_PATH)

SEED_RECORDS = [
    ("AWS Cloud Hosting Services", "Infrastructure", 4250.00, "PAID", "2026-08-01"),
    ("Acme Corp SaaS Subscription", "Software", 1200.00, "PAID", "2026-08-02"),
    ("Global Tech Solutions Hardware", "Equipment", 8500.00, "PAID", "2026-08-03"),
    ("Stripe Payment Processing Fees", "Financial Operations", 450.50, "SETTLED", "2026-08-04"),
    ("Google Workspace Enterprise", "Software", 890.00, "PAID", "2026-08-04"),
    ("Engineering Team Monthly Salaries", "Payroll", 45000.00, "PROCESSED", "2026-08-05"),
    ("Office Security Audit Consultant", "Professional Services", 3500.00, "PAID", "2026-08-06"),
    ("Datadog Monitoring License", "Software", 1850.00, "PAID", "2026-08-07"),
    ("GitHub Enterprise Cloud", "Software", 2100.00, "PAID", "2026-08-08"),
    ("Slack Business Communications", "Software", 650.00, "PAID", "2026-08-08"),
    ("Sales Team Q3 Commissions", "Payroll", 12500.00, "PENDING", "2026-08-09"),
    ("Legal Compliance Counsel Retainer", "Legal", 5000.00, "PAID", "2026-08-10"),
    ("Azure Backup Storage Vault", "Infrastructure", 950.00, "PAID", "2026-08-11"),
    ("CrowdStrike EDR Security Billing", "Security", 3200.00, "PAID", "2026-08-12"),
    ("Cloudflare Enterprise CDN", "Infrastructure", 1500.00, "PAID", "2026-08-12"),
    ("WeWork Main Office Rent", "Facilities", 14000.00, "PAID", "2026-08-13"),
    ("FedEx Express Documents", "Operations", 120.00, "PAID", "2026-08-14"),
    ("Zoom Video Enterprise Annual", "Software", 980.00, "PAID", "2026-08-14"),
    ("Confluent Kafka Managed Stream", "Infrastructure", 2400.00, "PAID", "2026-08-15"),
    ("Notion Corporate Team Plan", "Software", 420.00, "PAID", "2026-08-15"),
    ("OpenAI API Enterprise Credit", "AI Infrastructure", 6200.00, "PAID", "2026-08-16"),
    ("Apple MacBooks for Dev Onboarding", "Hardware", 7200.00, "PAID", "2026-08-16"),
    ("PagerDuty Incident Response", "Software", 780.00, "PAID", "2026-08-17"),
    ("PostgreSQL Managed DB Node", "Infrastructure", 1650.00, "PAID", "2026-08-17"),
    ("Executive Travel Expense Claims", "Travel", 2890.00, "REIMBURSED", "2026-08-18"),
    ("Deloitte Tax Advisory Retainer", "Financial Operations", 6800.00, "PAID", "2026-08-18"),
    ("1Password Business License", "Security", 340.00, "PAID", "2026-08-19"),
    ("HubSpot Marketing Automation", "Marketing", 2450.00, "PAID", "2026-08-19"),
    ("Figma Enterprise Design Team", "Software", 1100.00, "PAID", "2026-08-19"),
    ("SOC2 Type II Audit Final Fee", "Compliance", 18500.00, "PAID", "2026-08-19"),
    ("Sivaselvan.S Cloud Architecture Consultancy", "Professional Services", 3400.00, "PAID", "2026-08-10"),
    ("Sivaselvan.S Database Audit Retainer", "Compliance", 2800.00, "PAID", "2026-08-12"),
    ("Sivaselvan.S AI Infrastructure Support", "Software", 1950.00, "PAID", "2026-08-14"),
    ("Sivaselvan.S Security Review Services", "Security", 4100.00, "PAID", "2026-08-18"),
]

def _get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(force_reset: bool = False):
    """Initialize SQLite database and seed financial records if empty or forced."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS finance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_name TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                created_date TEXT NOT NULL
            )
        """)

        cursor.execute("SELECT COUNT(*) FROM finance_records")
        count = cursor.fetchone()[0]

        if count == 0 or force_reset:
            cursor.execute("DELETE FROM finance_records")
            cursor.executemany("""
                INSERT INTO finance_records (vendor_name, category, amount, status, created_date)
                VALUES (?, ?, ?, ?, ?)
            """, SEED_RECORDS)
            conn.commit()
            logger.info(f"SQLite DB initialized/reset with {len(SEED_RECORDS)} seed records at {DB_PATH}.")
    finally:
        conn.close()

def get_record_count() -> int:
    """Return total count of records in SQLite finance database."""
    init_db(force_reset=False)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM finance_records")
        return cursor.fetchone()[0]
    finally:
        conn.close()

def query_finance_records(limit: int = 200) -> dict:
    """Get database record count and full list of rows for inspection."""
    init_db(force_reset=False)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM finance_records")
        total_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT id, vendor_name, category, amount, status, created_date "
            "FROM finance_records ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = [dict(row) for row in cursor.fetchall()]

        return {
            "total_records": total_count,
            "records": rows,
            "message": f"SQLite Database currently contains {total_count} financial transaction records."
        }
    finally:
        conn.close()

def insert_finance_records(count: int = 1, vendor_name: str = "Acme Corp", category: str = "Software", amount: float = 1500.00) -> dict:
    """Insert new financial records into SQLite database."""
    init_db(force_reset=False)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_rows = [(f"{vendor_name} #{i+1}", category, amount, "PAID", today_str) for i in range(count)]
        cursor.executemany("""
            INSERT INTO finance_records (vendor_name, category, amount, status, created_date)
            VALUES (?, ?, ?, ?, ?)
        """, new_rows)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM finance_records")
        total_count = cursor.fetchone()[0]

        logger.info(f"Inserted {count} records into SQLite DB. New total: {total_count}")
        return {
            "inserted": count,
            "total_records": total_count,
            "message": f"Successfully inserted {count} financial records into SQLite DB. Total records now: {total_count}."
        }
    finally:
        conn.close()

def count_matching_records(search_term: str) -> int:
    """Return count of records matching search term in vendor_name or category."""
    init_db(force_reset=False)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM finance_records WHERE vendor_name LIKE ? OR category LIKE ?",
            (f"%{search_term}%", f"%{search_term}%")
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()

def delete_finance_records(query: str, record_count: int) -> dict:
    """Delete matching records from SQLite database."""
    init_db(force_reset=False)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM finance_records")
        initial_count = cursor.fetchone()[0]

        # Extract search term from query string
        filter_term = ""
        if "vendor" in query.lower() or "sivaselvan" in query.lower():
            for term in ["Sivaselvan.S", "Sivaselvan", "Acme", "AWS", "Google"]:
                if term.lower() in query.lower():
                    filter_term = term
                    break

        if filter_term:
            # Parameterized subquery — no f-string interpolation (SEC-3 fix)
            cursor.execute(
                "DELETE FROM finance_records WHERE id IN "
                "(SELECT id FROM finance_records WHERE vendor_name LIKE ? LIMIT ?)",
                (f"%{filter_term}%", record_count)
            )
        else:
            actual_to_delete = min(record_count, initial_count)
            if actual_to_delete > 0:
                # Parameterized — safe from SQL injection
                cursor.execute(
                    "DELETE FROM finance_records WHERE id IN "
                    "(SELECT id FROM finance_records ORDER BY id DESC LIMIT ?)",
                    (actual_to_delete,)
                )

        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM finance_records")
        new_count = cursor.fetchone()[0]

        deleted_actual = initial_count - new_count
        logger.info(f"Deleted {deleted_actual} records from SQLite DB (query='{query}'). Initial: {initial_count}, New: {new_count}")

        return {
            "deleted_requested": record_count,
            "deleted_actual": deleted_actual,
            "total_records": new_count,
            "message": f"Successfully deleted {deleted_actual} records from SQLite database matching query '{query}'. Total remaining records: {new_count}."
        }
    finally:
        conn.close()

def reset_db_to_seed() -> dict:
    """Reset SQLite database back to original seed records."""
    init_db(force_reset=True)
    count = get_record_count()
    return {
        "total_records": count,
        "message": f"SQLite Financial Database successfully reset to original {count} seed records."
    }
