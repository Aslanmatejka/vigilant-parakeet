#!/usr/bin/env python3
"""
Script to seed sample distribution centers with inventory
"""
import sys
import os

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Import models with full path
from models import Base, User, DistributionCenter, CenterInventory, UserRole, FoodCategory, PerishabilityLevel

load_dotenv(os.path.join(os.path.dirname(__file__), '../..', '.env'))
DATABASE_URL = os.getenv("DATABASE_URL")

print(f"Using database: {DATABASE_URL[:30]}...")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def seed_distribution_centers():
    db = SessionLocal()
    
    try:
        # Get a donor user (create one if doesn't exist)
        donor = db.query(User).filter(User.role == UserRole.DONOR).first()
        
        if not donor:
            print("No donor users found in database. Please create a donor user first.")
            return
        
        # Sample distribution centers
        centers_data = [
            {
                "name": "Downtown Food Hub",
                "description": "Central distribution center serving the downtown area",
                "address": "123 Market St, San Francisco, CA 94103",
                "coords_lat": 37.7749,
                "coords_lng": -122.4194,
                "phone": "(415) 555-0101",
                "hours": "Mon-Fri: 9AM-6PM, Sat: 10AM-4PM",
                "inventory": [
                    {"name": "Fresh Apples", "category": FoodCategory.FRUIT, "quantity": 50, "unit": "lbs", "perishability": PerishabilityLevel.MEDIUM},
                    {"name": "Canned Beans", "category": FoodCategory.PACKAGED, "quantity": 100, "unit": "cans", "perishability": PerishabilityLevel.LOW},
                    {"name": "Fresh Bread", "category": FoodCategory.BAKERY, "quantity": 30, "unit": "loaves", "perishability": PerishabilityLevel.HIGH},
                    {"name": "Bottled Water", "category": FoodCategory.WATER, "quantity": 200, "unit": "bottles", "perishability": PerishabilityLevel.LOW},
                ]
            },
            {
                "name": "Mission District Food Bank",
                "description": "Community food bank serving Mission District families",
                "address": "456 Valencia St, San Francisco, CA 94110",
                "coords_lat": 37.7599,
                "coords_lng": -122.4214,
                "phone": "(415) 555-0102",
                "hours": "Mon-Sat: 8AM-5PM",
                "inventory": [
                    {"name": "Fresh Vegetables Mix", "category": FoodCategory.PRODUCE, "quantity": 75, "unit": "lbs", "perishability": PerishabilityLevel.HIGH},
                    {"name": "Rice Bags", "category": FoodCategory.PACKAGED, "quantity": 40, "unit": "bags", "perishability": PerishabilityLevel.LOW},
                    {"name": "Prepared Meals", "category": FoodCategory.PREPARED, "quantity": 60, "unit": "servings", "perishability": PerishabilityLevel.HIGH},
                ]
            },
            {
                "name": "Sunset Community Pantry",
                "description": "Serving the Sunset and Richmond neighborhoods",
                "address": "789 Judah St, San Francisco, CA 94122",
                "coords_lat": 37.7625,
                "coords_lng": -122.4644,
                "phone": "(415) 555-0103",
                "hours": "Tue-Fri: 10AM-6PM, Sat: 9AM-3PM",
                "inventory": [
                    {"name": "Fresh Oranges", "category": FoodCategory.FRUIT, "quantity": 40, "unit": "lbs", "perishability": PerishabilityLevel.MEDIUM},
                    {"name": "Pasta Boxes", "category": FoodCategory.PACKAGED, "quantity": 80, "unit": "boxes", "perishability": PerishabilityLevel.LOW},
                    {"name": "Fresh Salad", "category": FoodCategory.PRODUCE, "quantity": 25, "unit": "bags", "perishability": PerishabilityLevel.HIGH},
                ]
            },
            {
                "name": "Do Good Warehouse",
                "description": "Main warehouse and distribution hub for community food programs",
                "address": "1900 Thau Way, Alameda, CA 94501",
                "coords_lat": 37.7652,
                "coords_lng": -122.2416,
                "phone": "510-522-6288",
                "hours": "Mon-Fri: 8AM-5PM",
                "inventory": [
                    {"name": "Canned Goods", "category": FoodCategory.PACKAGED, "quantity": 200, "unit": "cans", "perishability": PerishabilityLevel.LOW},
                    {"name": "Dry Pasta", "category": FoodCategory.PACKAGED, "quantity": 150, "unit": "boxes", "perishability": PerishabilityLevel.LOW},
                    {"name": "Rice", "category": FoodCategory.PACKAGED, "quantity": 100, "unit": "bags", "perishability": PerishabilityLevel.LOW},
                    {"name": "Fresh Produce", "category": FoodCategory.PRODUCE, "quantity": 80, "unit": "lbs", "perishability": PerishabilityLevel.HIGH},
                ]
            },
            {
                "name": "Ruby Bridges Elementary CC",
                "description": "Community center at Ruby Bridges Elementary School providing food assistance",
                "address": "351 Jack London Ave, Alameda, CA 94501",
                "coords_lat": 37.7714,
                "coords_lng": -122.2628,
                "phone": "510-748-4006",
                "hours": "Mon-Fri: 3PM-6PM, Sat: 10AM-2PM",
                "inventory": [
                    {"name": "Fresh Fruit", "category": FoodCategory.FRUIT, "quantity": 50, "unit": "lbs", "perishability": PerishabilityLevel.MEDIUM},
                    {"name": "Snack Packs", "category": FoodCategory.PACKAGED, "quantity": 120, "unit": "packs", "perishability": PerishabilityLevel.LOW},
                    {"name": "Juice Boxes", "category": FoodCategory.WATER, "quantity": 100, "unit": "boxes", "perishability": PerishabilityLevel.MEDIUM},
                    {"name": "Breakfast Items", "category": FoodCategory.PACKAGED, "quantity": 80, "unit": "items", "perishability": PerishabilityLevel.LOW},
                ]
            },
            {
                "name": "NEA/ACLC CC",
                "description": "Nea Community Learning Center providing food distribution services",
                "address": "1900 3rd St, Alameda, CA 94501",
                "coords_lat": 37.7653,
                "coords_lng": -122.2594,
                "phone": "510-748-4008",
                "hours": "Tue-Sat: 9AM-5PM",
                "inventory": [
                    {"name": "Fresh Vegetables", "category": FoodCategory.PRODUCE, "quantity": 70, "unit": "lbs", "perishability": PerishabilityLevel.HIGH},
                    {"name": "Bread Loaves", "category": FoodCategory.BAKERY, "quantity": 40, "unit": "loaves", "perishability": PerishabilityLevel.HIGH},
                    {"name": "Canned Soup", "category": FoodCategory.PACKAGED, "quantity": 90, "unit": "cans", "perishability": PerishabilityLevel.LOW},
                    {"name": "Bottled Water", "category": FoodCategory.WATER, "quantity": 150, "unit": "bottles", "perishability": PerishabilityLevel.LOW},
                ]
            },
            {
                "name": "Academy of Alameda CC",
                "description": "Academy of Alameda community center offering food assistance programs",
                "address": "401 Pacific Ave, Alameda, CA 94501",
                "coords_lat": 37.7707,
                "coords_lng": -122.2636,
                "phone": "510-748-4017",
                "hours": "Mon-Fri: 8AM-4PM",
                "inventory": [
                    {"name": "Fresh Bananas", "category": FoodCategory.FRUIT, "quantity": 45, "unit": "lbs", "perishability": PerishabilityLevel.HIGH},
                    {"name": "Cereal Boxes", "category": FoodCategory.PACKAGED, "quantity": 70, "unit": "boxes", "perishability": PerishabilityLevel.LOW},
                    {"name": "Peanut Butter", "category": FoodCategory.PACKAGED, "quantity": 50, "unit": "jars", "perishability": PerishabilityLevel.LOW},
                    {"name": "Fresh Lettuce", "category": FoodCategory.PRODUCE, "quantity": 30, "unit": "heads", "perishability": PerishabilityLevel.HIGH},
                ]
            },
            {
                "name": "Island HS CC",
                "description": "Island High School community center providing food distribution to students and families",
                "address": "2323 Pacific Ave, Alameda, CA 94501",
                "coords_lat": 37.7721,
                "coords_lng": -122.2651,
                "phone": "510-748-4024",
                "hours": "Mon-Fri: 3PM-6PM",
                "inventory": [
                    {"name": "Granola Bars", "category": FoodCategory.PACKAGED, "quantity": 150, "unit": "bars", "perishability": PerishabilityLevel.LOW},
                    {"name": "Apple Juice", "category": FoodCategory.WATER, "quantity": 80, "unit": "bottles", "perishability": PerishabilityLevel.MEDIUM},
                    {"name": "Fresh Carrots", "category": FoodCategory.PRODUCE, "quantity": 40, "unit": "lbs", "perishability": PerishabilityLevel.MEDIUM},
                    {"name": "Sandwich Bread", "category": FoodCategory.BAKERY, "quantity": 50, "unit": "loaves", "perishability": PerishabilityLevel.HIGH},
                ]
            },
            {
                "name": "Encinal Jr Sr High School CC",
                "description": "Encinal Junior Senior High School community center serving students and local families",
                "address": "210 Central Ave, Alameda, CA 94501",
                "coords_lat": 37.7664,
                "coords_lng": -122.2554,
                "phone": "510-748-4023",
                "hours": "Mon-Fri: 2:30PM-5:30PM, Sat: 10AM-2PM",
                "inventory": [
                    {"name": "Fresh Apples", "category": FoodCategory.FRUIT, "quantity": 60, "unit": "lbs", "perishability": PerishabilityLevel.MEDIUM},
                    {"name": "Mac & Cheese", "category": FoodCategory.PACKAGED, "quantity": 85, "unit": "boxes", "perishability": PerishabilityLevel.LOW},
                    {"name": "Fresh Tomatoes", "category": FoodCategory.PRODUCE, "quantity": 35, "unit": "lbs", "perishability": PerishabilityLevel.HIGH},
                    {"name": "Fruit Cups", "category": FoodCategory.PACKAGED, "quantity": 100, "unit": "cups", "perishability": PerishabilityLevel.LOW},
                ]
            }
        ]
        
        for center_data in centers_data:
            # Check if center already exists
            existing = db.query(DistributionCenter).filter(
                DistributionCenter.name == center_data["name"]
            ).first()
            
            if existing:
                print(f"Center '{center_data['name']}' already exists, skipping...")
                continue
            
            # Create center
            inventory_items = center_data.pop("inventory", [])
            center = DistributionCenter(
                owner_id=donor.id,
                **center_data
            )
            
            db.add(center)
            db.flush()  # Get the center ID
            
            # Add inventory items
            for item_data in inventory_items:
                expiration_date = None
                if item_data.get('perishability') == PerishabilityLevel.HIGH:
                    expiration_date = datetime.utcnow() + timedelta(days=3)
                elif item_data.get('perishability') == PerishabilityLevel.MEDIUM:
                    expiration_date = datetime.utcnow() + timedelta(days=14)
                
                inventory_item = CenterInventory(
                    center_id=center.id,
                    name=item_data['name'],
                    category=item_data['category'],
                    quantity=item_data['quantity'],
                    unit=item_data['unit'],
                    perishability=item_data.get('perishability'),
                    expiration_date=expiration_date,
                    is_available=True
                )
                db.add(inventory_item)
            
            print(f"✓ Created center: {center_data['name']} with {len(inventory_items)} items")
        
        db.commit()
        print("\n✅ Successfully seeded distribution centers!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding data: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    seed_distribution_centers()
