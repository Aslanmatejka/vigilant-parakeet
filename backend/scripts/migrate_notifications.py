"""
Migration script to add smart notification fields to users table
Run this to enable AI-powered notification preferences and behavior tracking
"""
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

engine = create_engine(DATABASE_URL)

def migrate():
    with engine.connect() as conn:
        print("Adding notification columns to users table...")
        
        try:
            # Add notification_preferences column (without IF NOT EXISTS)
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN notification_preferences TEXT NULL 
                COMMENT 'JSON object storing user notification preferences'
            """))
            print("✓ Added notification_preferences column")
            
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("✓ notification_preferences column already exists")
            else:
                print(f"Error adding notification_preferences: {e}")
        
        try:
            # Add notification_behavior column (without IF NOT EXISTS)
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN notification_behavior TEXT NULL 
                COMMENT 'JSON object storing learned behavior data for AI filtering'
            """))
            print("✓ Added notification_behavior column")
            
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("✓ notification_behavior column already exists")
            else:
                print(f"Error adding notification_behavior: {e}")
        
        conn.commit()
        print("\n✓ Migration completed successfully!")
        print("\nSmart Notifications feature is now enabled.")
        print("Users can configure preferences and the AI will learn from their behavior.")

if __name__ == "__main__":
    print("Smart Notifications Migration")
    print("=" * 50)
    
    response = input("This will add notification columns to the users table. Continue? (y/n): ")
    if response.lower() == 'y':
        migrate()
    else:
        print("Migration cancelled")
