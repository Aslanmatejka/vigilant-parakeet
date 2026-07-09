#!/usr/bin/env python3
"""
Migration script to add pickup verification fields to food_resources table
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from project root
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

def run_migration():
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False
    
    database_url = database_url.strip().strip('"').strip("'")
    
    print(f"🔗 Connecting to database...")
    print(f"   URL: {database_url.split('@')[1] if '@' in database_url else 'hidden'}")
    
    try:
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            print("\n📝 Adding pickup verification columns to food_resources table...")
            
            columns_to_add = [
                ("verification_status", "ENUM('pending', 'before_verified', 'completed', 'not_required') DEFAULT 'not_required'"),
                ("before_photo", "TEXT NULL"),
                ("after_photo", "TEXT NULL"),
                ("before_verified_at", "DATETIME NULL"),
                ("after_verified_at", "DATETIME NULL"),
                ("pickup_notes", "TEXT NULL")
            ]
            
            for column_name, column_def in columns_to_add:
                try:
                    query = text(f"ALTER TABLE food_resources ADD COLUMN {column_name} {column_def}")
                    conn.execute(query)
                    conn.commit()
                    print(f"   ✓ Added column: {column_name}")
                except Exception as e:
                    if "Duplicate column name" in str(e):
                        print(f"   ⚠ Column {column_name} already exists, skipping")
                    else:
                        raise e
            
            print("\n✅ Migration completed successfully!")
            
            # Verify the changes
            print("\n🔍 Verifying new columns...")
            result = conn.execute(text("DESCRIBE food_resources"))
            columns = [row[0] for row in result]
            
            new_columns = [col[0] for col in columns_to_add]
            for col in new_columns:
                if col in columns:
                    print(f"   ✓ {col} - present")
                else:
                    print(f"   ❌ {col} - MISSING!")
            
            return True
            
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("  Pickup Verification Migration Script")
    print("=" * 60)
    print()
    
    success = run_migration()
    
    if success:
        print("\n" + "=" * 60)
        print("  Migration completed successfully! ✅")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("  Migration failed! ❌")
        print("=" * 60)
        sys.exit(1)
