#!/usr/bin/env python3
"""
Migration script to create distribution center tables
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '../..', '.env'))
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env file")
    sys.exit(1)

print(f"Using database: {DATABASE_URL[:30]}...")
engine = create_engine(DATABASE_URL)

# SQL to create distribution_centers table
create_distribution_centers = """
CREATE TABLE IF NOT EXISTS distribution_centers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    owner_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    address VARCHAR(255) NOT NULL,
    coords_lat FLOAT NOT NULL,
    coords_lng FLOAT NOT NULL,
    phone VARCHAR(255),
    hours TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# SQL to create center_inventory table
create_center_inventory = """
CREATE TABLE IF NOT EXISTS center_inventory (
    id INT PRIMARY KEY AUTO_INCREMENT,
    center_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category ENUM('produce', 'prepared', 'packaged', 'bakery', 'water', 'fruit', 'leftovers') NOT NULL,
    quantity FLOAT NOT NULL,
    unit VARCHAR(255) NOT NULL,
    perishability ENUM('high', 'medium', 'low'),
    expiration_date DATETIME,
    images TEXT,
    is_available BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (center_id) REFERENCES distribution_centers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

def run_migration():
    try:
        with engine.connect() as conn:
            print("Creating distribution_centers table...")
            conn.execute(text(create_distribution_centers))
            conn.commit()
            print("✓ distribution_centers table created")
            
            print("Creating center_inventory table...")
            conn.execute(text(create_center_inventory))
            conn.commit()
            print("✓ center_inventory table created")
            
            print("\n✅ Migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
