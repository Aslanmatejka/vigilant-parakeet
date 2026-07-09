"""
Migration script to add referral code columns to users table
Run this with: python3 backend/scripts/add_referral_columns.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import random
import string

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")
engine = create_engine(DATABASE_URL)

def generate_referral_code():
    """Generate a unique referral code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def add_referral_columns():
    """Add referral_code and referred_by_code columns to users table"""
    with engine.connect() as conn:
        try:
            # Check if columns already exist
            result = conn.execute(text("SHOW COLUMNS FROM users LIKE 'referral_code'"))
            if result.fetchone():
                print("✅ referral_code column already exists")
            else:
                # Add referral_code column
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN referral_code VARCHAR(20) UNIQUE NULL,
                    ADD INDEX idx_referral_code (referral_code)
                """))
                print("✅ Added referral_code column")
            
            # Check for referred_by_code
            result = conn.execute(text("SHOW COLUMNS FROM users LIKE 'referred_by_code'"))
            if result.fetchone():
                print("✅ referred_by_code column already exists")
            else:
                # Add referred_by_code column
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN referred_by_code VARCHAR(20) NULL,
                    ADD INDEX idx_referred_by_code (referred_by_code)
                """))
                print("✅ Added referred_by_code column")
            
            conn.commit()
            
            # Generate referral codes for existing users
            result = conn.execute(text("SELECT id FROM users WHERE referral_code IS NULL"))
            users = result.fetchall()
            
            for user in users:
                code = generate_referral_code()
                # Ensure uniqueness
                while True:
                    check = conn.execute(text("SELECT id FROM users WHERE referral_code = :code"), {"code": code})
                    if not check.fetchone():
                        break
                    code = generate_referral_code()
                
                conn.execute(
                    text("UPDATE users SET referral_code = :code WHERE id = :id"),
                    {"code": code, "id": user[0]}
                )
                print(f"✅ Generated referral code {code} for user {user[0]}")
            
            conn.commit()
            print(f"\n✅ Successfully updated {len(users)} users with referral codes")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    print("🔧 Adding referral code columns to users table...")
    add_referral_columns()
    print("\n✅ Migration completed successfully!")
