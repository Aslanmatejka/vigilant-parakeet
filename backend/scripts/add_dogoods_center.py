"""
Add Dogood's store as a distribution center
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models import DistributionCenter

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'mysql+pymysql://admin:foodmaps2024@database-1.c9um4qfazhpa.us-east-2.rds.amazonaws.com:3306/foodmaps')

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

try:
    # Add Dogood's store
    dogoods = DistributionCenter(
        owner_id=1,
        name="Dogood's Grocery & Market",
        description="Local grocery store and community market serving fresh food to the neighborhood",
        address="550 Irving St, San Francisco, CA 94122",
        coords_lat=37.7634,
        coords_lng=-122.4642,
        phone="(415) 555-0104",
        hours="Mon-Sun: 7AM-10PM",
        is_active=True
    )
    
    session.add(dogoods)
    session.commit()
    
    print(f"✅ Successfully added Dogood's store as distribution center (ID: {dogoods.id})")
    
except Exception as e:
    session.rollback()
    print(f"❌ Error adding Dogood's store: {e}")
finally:
    session.close()
