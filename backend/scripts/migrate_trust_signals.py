#!/usr/bin/env python3
"""
Migration script to add Community Trust Signal fields to users and distribution_centers tables.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

def migrate_trust_signals():
    """Add trust signal columns to users and distribution_centers tables"""
    
    # Load environment
    load_dotenv(Path(__file__).parent.parent.parent / '.env')
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment")
    
    engine = create_engine(DATABASE_URL)
    
    print("🔄 Starting Community Trust Signals migration...")
    
    with engine.connect() as conn:
        # Add columns to users table
        user_columns = [
            ("verified_by_aglf", "BOOLEAN DEFAULT FALSE"),
            ("school_partner", "BOOLEAN DEFAULT FALSE"),
            ("partner_badge", "VARCHAR(100) NULL"),
            ("partner_since", "DATETIME NULL"),
            ("last_active", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ]
        
        print("\n📊 Adding columns to users table...")
        for col_name, col_def in user_columns:
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                print(f"  ✅ Added {col_name}")
            except Exception as e:
                if "Duplicate column name" in str(e):
                    print(f"  ⏭️  {col_name} already exists")
                else:
                    print(f"  ⚠️  Error adding {col_name}: {e}")
        
        # Add columns to distribution_centers table
        center_columns = [
            ("verified_by_aglf", "BOOLEAN DEFAULT FALSE"),
            ("school_partner", "BOOLEAN DEFAULT FALSE"),
            ("partner_badge", "VARCHAR(100) NULL"),
            ("partner_since", "DATETIME NULL"),
            ("last_updated", "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ]
        
        print("\n📊 Adding columns to distribution_centers table...")
        for col_name, col_def in center_columns:
            try:
                conn.execute(text(f"ALTER TABLE distribution_centers ADD COLUMN {col_name} {col_def}"))
                print(f"  ✅ Added {col_name}")
            except Exception as e:
                if "Duplicate column name" in str(e):
                    print(f"  ⏭️  {col_name} already exists")
                else:
                    print(f"  ⚠️  Error adding {col_name}: {e}")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        # Update last_active for existing users
        print("\n🔄 Updating last_active for existing users...")
        try:
            conn.execute(text("UPDATE users SET last_active = COALESCE(created_at, NOW()) WHERE last_active IS NULL"))
            conn.commit()
            print("  ✅ Updated last_active timestamps")
        except Exception as e:
            print(f"  ⚠️  Error updating timestamps: {e}")

if __name__ == "__main__":
    migrate_trust_signals()
