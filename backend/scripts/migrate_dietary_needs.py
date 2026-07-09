#!/usr/bin/env python3
"""
Migration script to add dietary needs fields to users table
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from project root (2 levels up from this script)
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

def run_migration():
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False
    
    # Clean up the URL (remove quotes and whitespace)
    database_url = database_url.strip().strip('"').strip("'")
    
    print(f"🔗 Connecting to database...")
    print(f"   URL: {database_url.split('@')[1] if '@' in database_url else 'hidden'}")
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            print("\n📝 Adding dietary needs columns to users table...")
            
            # Add columns one by one
            columns_to_add = [
                ("dietary_restrictions", "TEXT NULL"),
                ("allergies", "TEXT NULL"),
                ("household_size", "INT DEFAULT 1"),
                ("preferred_categories", "TEXT NULL"),
                ("special_needs", "TEXT NULL")
            ]
            
            for column_name, column_def in columns_to_add:
                try:
                    query = text(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
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
            result = conn.execute(text("DESCRIBE users"))
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
    print("  Dietary Needs Migration Script")
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
