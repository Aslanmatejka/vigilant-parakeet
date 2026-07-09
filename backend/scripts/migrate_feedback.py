"""
Database migration script to add feedback table
Run this script to create the feedback table in your database
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
from pathlib import Path

# Load .env from project root (two levels up from this script)
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Get database connection from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found in .env file")
    
# Remove spaces if any (in case .env has "KEY = value" format)
DATABASE_URL = DATABASE_URL.strip().strip('"')

def migrate():
    engine = create_engine(DATABASE_URL)
    
    migration_sql = """
    CREATE TABLE IF NOT EXISTS feedback (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NULL,
        type ENUM('bug', 'feature_request', 'general', 'error_report', 'improvement') DEFAULT 'general',
        subject VARCHAR(255) NOT NULL,
        message TEXT NOT NULL,
        url VARCHAR(512) NULL,
        user_agent VARCHAR(512) NULL,
        screenshot TEXT NULL,
        error_stack TEXT NULL,
        status ENUM('new', 'reviewing', 'in_progress', 'resolved', 'closed') DEFAULT 'new',
        admin_notes TEXT NULL,
        email VARCHAR(255) NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
        INDEX idx_status (status),
        INDEX idx_type (type),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    try:
        with engine.connect() as conn:
            print("Creating feedback table...")
            conn.execute(text(migration_sql))
            conn.commit()
            print("✓ Feedback table created successfully!")
            
            # Verify table was created
            result = conn.execute(text("SHOW TABLES LIKE 'feedback'"))
            if result.fetchone():
                print("✓ Table verification successful")
            else:
                print("⚠ Warning: Table not found after creation")
                
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        raise

if __name__ == "__main__":
    print("Running feedback table migration...")
    migrate()
    print("Migration complete!")
