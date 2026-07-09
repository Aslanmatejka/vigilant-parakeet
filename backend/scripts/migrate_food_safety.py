#!/usr/bin/env python3
"""
Migration script for Food Safety Checklist feature
Adds safety tracking columns to food_resources table
"""
import sys
import os

# Add parent directory to path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.app import engine
from sqlalchemy import text

def run_migration():
    """Execute the migration using the backend's database engine"""
    print("🛡️ Starting Food Safety Checklist Migration...")
    print(f"Using existing backend database connection")
    
    try:
        with engine.connect() as connection:
            # Start transaction
            trans = connection.begin()
            
            try:
                print("\n📊 Adding safety tracking fields to food_resources table...")
                
                # Add storage_temperature column
                try:
                    connection.execute(text("""
                        ALTER TABLE food_resources 
                        ADD COLUMN storage_temperature FLOAT DEFAULT NULL 
                        COMMENT 'Temperature in Fahrenheit where food is stored'
                    """))
                    print("  ✅ Added storage_temperature column")
                except Exception as e:
                    if "Duplicate column name" in str(e):
                        print("  ℹ️  storage_temperature column already exists")
                    else:
                        raise
                
                # Add boolean storage type columns
                storage_columns = [
                    ('is_refrigerated', 'Whether food is stored in refrigerator'),
                    ('is_frozen', 'Whether food is stored in freezer')
                ]
                
                for col_name, comment in storage_columns:
                    try:
                        connection.execute(text(f"""
                            ALTER TABLE food_resources 
                            ADD COLUMN {col_name} BOOLEAN DEFAULT FALSE 
                            COMMENT '{comment}'
                        """))
                        print(f"  ✅ Added {col_name} column")
                    except Exception as e:
                        if "Duplicate column name" in str(e):
                            print(f"  ℹ️  {col_name} column already exists")
                        else:
                            raise
                
                # Add packaging_condition column
                try:
                    connection.execute(text("""
                        ALTER TABLE food_resources 
                        ADD COLUMN packaging_condition VARCHAR(50) DEFAULT 'good' 
                        COMMENT 'Condition of packaging: excellent, good, fair, poor'
                    """))
                    print("  ✅ Added packaging_condition column")
                except Exception as e:
                    if "Duplicate column name" in str(e):
                        print("  ℹ️  packaging_condition column already exists")
                    else:
                        raise
                
                # Add safety checklist status columns
                safety_columns = [
                    ('safety_checklist_passed', 'BOOLEAN', 'FALSE', 'Whether food passed safety checklist'),
                    ('safety_score', 'INT', '0', 'Safety score from 0-100'),
                    ('safety_notes', 'TEXT', 'NULL', 'Additional safety observations'),
                    ('safety_last_checked', 'DATETIME', 'NULL', 'When safety check was last performed')
                ]
                
                for col_name, col_type, default, comment in safety_columns:
                    try:
                        default_clause = f"DEFAULT {default}" if default != 'NULL' else ''
                        connection.execute(text(f"""
                            ALTER TABLE food_resources 
                            ADD COLUMN {col_name} {col_type} {default_clause}
                            COMMENT '{comment}'
                        """))
                        print(f"  ✅ Added {col_name} column")
                    except Exception as e:
                        if "Duplicate column name" in str(e):
                            print(f"  ℹ️  {col_name} column already exists")
                        else:
                            raise
                
                # Commit transaction
                trans.commit()
                
                print("\n✅ Migration completed successfully!")
                print("\n📋 Summary:")
                print("  • Added storage_temperature (FLOAT) - temperature tracking in °F")
                print("  • Added is_refrigerated (BOOLEAN) - refrigeration status")
                print("  • Added is_frozen (BOOLEAN) - frozen storage status")
                print("  • Added packaging_condition (VARCHAR) - packaging quality rating")
                print("  • Added safety_checklist_passed (BOOLEAN) - overall safety status")
                print("  • Added safety_score (INT) - 0-100 safety score")
                print("  • Added safety_notes (TEXT) - additional safety observations")
                print("  • Added safety_last_checked (DATETIME) - last check timestamp")
                print("\n🎯 Food Safety Checklist feature is now ready!")
                
                return True
                
            except Exception as e:
                trans.rollback()
                print(f"\n❌ Migration failed: {str(e)}")
                raise
                
    except Exception as e:
        print(f"\n❌ Database connection failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
