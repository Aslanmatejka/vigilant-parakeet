#!/usr/bin/env python3
"""
Delete Dogood's Grocery & Market distribution center
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models import DistributionCenter

# Use DATABASE_URL from the environment — never commit credentials.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL in the environment before running this script.")

print(f"Using database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else '(configured)'}...")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

try:
    center = session.query(DistributionCenter).filter(
        DistributionCenter.name == "Dogood's Grocery & Market"
    ).first()
    
    if center:
        center_id = center.id
        session.delete(center)
        session.commit()
        print(f"✅ Successfully deleted Dogood's Grocery & Market (ID: {center_id})")
    else:
        print("❌ Dogood's Grocery & Market not found in database")
        
except Exception as e:
    session.rollback()
    print(f"❌ Error deleting center: {e}")
finally:
    session.close()
