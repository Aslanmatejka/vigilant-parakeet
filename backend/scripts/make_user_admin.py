#!/usr/bin/env python3
"""
Script to make a user an admin by email
Usage: python make_user_admin.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import User
from dotenv import load_dotenv

load_dotenv()

def make_admin(email):
    """Update user role to admin"""
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        return False
    
    # Create engine and session
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"❌ User with email '{email}' not found")
            return False
        
        print(f"Found user: {user.name} ({user.email})")
        print(f"Current role: {user.role}")
        
        user.role = 'admin'
        db.commit()
        
        print(f"✅ Successfully updated {user.name} to admin role")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    email = "aslanabdulkarim84@gmail.com"
    make_admin(email)
