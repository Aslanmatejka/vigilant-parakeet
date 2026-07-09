#!/usr/bin/env python3
"""
Migration script for Safety and Trust features - Version 2
Uses the backend's existing database connection
"""
import sys
import os

# Add parent directory to path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.app import engine
from sqlalchemy import text

def run_migration():
    """Execute the migration using the backend's database engine"""
    print("🛡️ Starting Safety and Trust Features Migration (v2)...")
    print(f"Using existing backend database connection")
    
    try:
        with engine.connect() as connection:
            # Start transaction
            trans = connection.begin()
            
            try:
                print("\n📊 Adding trust and verification fields to users table...")
                
                # Add trust_score column
                try:
                    connection.execute(text("""
                        ALTER TABLE users 
                        ADD COLUMN trust_score INT DEFAULT 50 
                        COMMENT 'User trust score (0-100)'
                    """))
                    print("  ✅ Added trust_score column")
                except Exception as e:
                    if "Duplicate column name" in str(e):
                        print("  ℹ️  trust_score column already exists")
                    else:
                        raise
                
                # Add verification boolean columns
                verification_columns = [
                    'email_verified',
                    'phone_verified', 
                    'id_verified',
                    'address_verified'
                ]
                
                for col in verification_columns:
                    try:
                        connection.execute(text(f"""
                            ALTER TABLE users 
                            ADD COLUMN {col} BOOLEAN DEFAULT FALSE 
                            COMMENT 'Whether {col.replace("_", " ")} is verified'
                        """))
                        print(f"  ✅ Added {col} column")
                    except Exception as e:
                        if "Duplicate column name" in str(e):
                            print(f"  ℹ️  {col} column already exists")
                        else:
                            raise
                
                # Add engagement tracking columns
                engagement_columns = [
                    ('completed_exchanges', 'Number of successfully completed exchanges'),
                    ('positive_feedback', 'Count of positive feedback received'),
                    ('negative_feedback', 'Count of negative feedback received'),
                    ('verified_pickups', 'Number of verified pickups completed')
                ]
                
                for col_name, comment in engagement_columns:
                    try:
                        connection.execute(text(f"""
                            ALTER TABLE users 
                            ADD COLUMN {col_name} INT DEFAULT 0 
                            COMMENT '{comment}'
                        """))
                        print(f"  ✅ Added {col_name} column")
                    except Exception as e:
                        if "Duplicate column name" in str(e):
                            print(f"  ℹ️  {col_name} column already exists")
                        else:
                            raise
                
                print("\n🗄️ Creating safety_reports table...")
                
                # Create safety_reports table
                try:
                    connection.execute(text("""
                        CREATE TABLE IF NOT EXISTS safety_reports (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            reporter_id INT NOT NULL,
                            reported_user_id INT,
                            listing_id INT,
                            report_type ENUM(
                                'unsafe_food',
                                'no_show', 
                                'harassment',
                                'fraud',
                                'inappropriate',
                                'safety_concern',
                                'other'
                            ) NOT NULL,
                            description TEXT NOT NULL,
                            evidence TEXT,
                            status ENUM(
                                'pending',
                                'under_review',
                                'resolved',
                                'dismissed'
                            ) DEFAULT 'pending',
                            admin_notes TEXT,
                            resolved_by INT,
                            resolved_at DATETIME,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            
                            FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE,
                            FOREIGN KEY (reported_user_id) REFERENCES users(id) ON DELETE SET NULL,
                            FOREIGN KEY (listing_id) REFERENCES food_resources(id) ON DELETE SET NULL,
                            FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL,
                            
                            INDEX idx_reporter (reporter_id),
                            INDEX idx_reported_user (reported_user_id),
                            INDEX idx_status (status),
                            INDEX idx_created (created_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                        COMMENT='Safety and trust incident reports'
                    """))
                    print("  ✅ Created safety_reports table")
                except Exception as e:
                    if "already exists" in str(e):
                        print("  ℹ️  safety_reports table already exists")
                    else:
                        raise
                
                # Commit transaction
                trans.commit()
                
                print("\n✅ Migration completed successfully!")
                print("\n📋 Summary:")
                print("  • Added 9 columns to users table (trust_score, 4 verifications, 4 engagement metrics)")
                print("  • Created safety_reports table with full workflow tracking")
                print("  • All existing users initialized with trust_score = 50")
                
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
