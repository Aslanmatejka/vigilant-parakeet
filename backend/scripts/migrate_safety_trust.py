#!/usr/bin/env python3
"""
Migration script to add Safety and Trust features to Food Maps
Adds trust scores, verification fields, and safety report tables
"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection settings
DB_HOST = os.getenv('DB_HOST', 'database-1.c9um4qfazhpa.us-east-2.rds.amazonaws.com')
DB_PORT = int(os.getenv('DB_PORT', 3306))
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'foodmaps2024')
DB_NAME = os.getenv('DB_NAME', 'foodmaps')

def run_migration():
    print("🛡️ Starting Safety and Trust Features Migration...")
    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    connection = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4'
    )
    
    try:
        with connection.cursor() as cursor:
            # Add trust and verification fields to users table
            print("\n📊 Adding trust score and verification fields to users table...")
            
            user_columns = [
                ("trust_score", "INT DEFAULT 50"),
                ("email_verified", "BOOLEAN DEFAULT FALSE"),
                ("phone_verified", "BOOLEAN DEFAULT FALSE"),
                ("id_verified", "BOOLEAN DEFAULT FALSE"),
                ("address_verified", "BOOLEAN DEFAULT FALSE"),
                ("completed_exchanges", "INT DEFAULT 0"),
                ("positive_feedback", "INT DEFAULT 0"),
                ("negative_feedback", "INT DEFAULT 0"),
                ("verified_pickups", "INT DEFAULT 0")
            ]
            
            for col_name, col_def in user_columns:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                    print(f"  ✓ Added column: {col_name}")
                except pymysql.err.OperationalError as e:
                    if "Duplicate column name" in str(e):
                        print(f"  ⊙ Column already exists: {col_name}")
                    else:
                        raise
            
            connection.commit()
            
            # Create safety_reports table
            print("\n🚨 Creating safety_reports table...")
            
            create_reports_table = """
            CREATE TABLE IF NOT EXISTS safety_reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                reporter_id INT NOT NULL,
                reported_user_id INT NULL,
                listing_id INT NULL,
                report_type ENUM('unsafe_food', 'no_show', 'harassment', 'fraud', 'inappropriate', 'safety_concern', 'other') NOT NULL,
                description TEXT NOT NULL,
                evidence TEXT NULL,
                status ENUM('pending', 'under_review', 'resolved', 'dismissed') DEFAULT 'pending',
                reviewed_by INT NULL,
                reviewed_at DATETIME NULL,
                resolution_notes TEXT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (reporter_id) REFERENCES users(id),
                FOREIGN KEY (reported_user_id) REFERENCES users(id),
                FOREIGN KEY (listing_id) REFERENCES food_resources(id),
                FOREIGN KEY (reviewed_by) REFERENCES users(id),
                INDEX idx_reporter (reporter_id),
                INDEX idx_reported_user (reported_user_id),
                INDEX idx_status (status),
                INDEX idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            
            cursor.execute(create_reports_table)
            print("  ✓ safety_reports table created successfully")
            connection.commit()
            
            # Verify all columns were added
            print("\n✅ Verification - Checking users table columns:")
            cursor.execute("DESCRIBE users")
            columns = cursor.fetchall()
            column_names = [col[0] for col in columns]
            
            for col_name, _ in user_columns:
                if col_name in column_names:
                    print(f"  ✓ {col_name} - present")
                else:
                    print(f"  ✗ {col_name} - MISSING")
            
            # Verify safety_reports table
            print("\n✅ Verification - Checking safety_reports table:")
            cursor.execute("SHOW TABLES LIKE 'safety_reports'")
            if cursor.fetchone():
                print("  ✓ safety_reports table exists")
                cursor.execute("DESCRIBE safety_reports")
                report_columns = cursor.fetchall()
                print(f"  ✓ Table has {len(report_columns)} columns")
            else:
                print("  ✗ safety_reports table MISSING")
            
            # Initialize trust scores for existing users
            print("\n🎯 Initializing trust scores for existing users...")
            cursor.execute("""
                UPDATE users 
                SET trust_score = 50 
                WHERE trust_score IS NULL OR trust_score = 0
            """)
            updated = cursor.rowcount
            print(f"  ✓ Initialized trust scores for {updated} users")
            connection.commit()
            
            print("\n🎉 Migration completed successfully!")
            print("\n📋 Summary:")
            print(f"  • Added 9 trust/verification columns to users table")
            print(f"  • Created safety_reports table")
            print(f"  • Initialized trust scores for existing users")
            print("\n✨ Safety and Trust features are now active!")
            
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        connection.rollback()
        raise
    finally:
        connection.close()
        print("\n🔌 Database connection closed")

if __name__ == "__main__":
    run_migration()
