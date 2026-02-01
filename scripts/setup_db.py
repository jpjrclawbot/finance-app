#!/usr/bin/env python3
"""Database setup script."""

import subprocess
import sys
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_FILE = PROJECT_ROOT / "db" / "schema.sql"


def main():
    """Set up the database."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost/finance_app")
    
    # Parse connection string
    # Format: postgresql://user:pass@host:port/dbname
    if "@" in db_url:
        # Has auth
        parts = db_url.replace("postgresql://", "").split("@")
        auth = parts[0]
        host_db = parts[1]
    else:
        auth = None
        host_db = db_url.replace("postgresql://", "")
    
    if "/" in host_db:
        host_port, dbname = host_db.rsplit("/", 1)
    else:
        host_port = host_db
        dbname = "finance_app"
    
    print(f"Setting up database: {dbname}")
    
    # Create database if not exists
    try:
        subprocess.run(
            ["createdb", dbname],
            capture_output=True,
            check=False,
        )
        print(f"Created database: {dbname}")
    except Exception:
        print(f"Database {dbname} may already exist")
    
    # Run schema
    print(f"Applying schema from: {SCHEMA_FILE}")
    result = subprocess.run(
        ["psql", "-d", dbname, "-f", str(SCHEMA_FILE)],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"Error applying schema: {result.stderr}")
        sys.exit(1)
    
    print("Schema applied successfully!")
    print(result.stdout)


if __name__ == "__main__":
    main()
