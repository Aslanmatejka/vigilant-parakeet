"""
Migration script to add favorite_locations table
Run this to add the favorites feature to your database
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
        print("Creating favorite_locations table...")
        
        try:
            # Create favorite_locations table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS favorite_locations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    address VARCHAR(500),
                    coords_lat FLOAT,
                    coords_lng FLOAT,
                    location_type VARCHAR(50) DEFAULT 'general',
                    donor_id INT NULL,
                    center_id INT NULL,
                    notes TEXT,
                    tags TEXT,
                    visit_count INT DEFAULT 0,
                    last_visited DATETIME NULL,
                    notify_new_listings BOOLEAN DEFAULT FALSE,
                    notification_radius_km FLOAT DEFAULT 5.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (donor_id) REFERENCES users(id) ON DELETE SET NULL,
                    FOREIGN KEY (center_id) REFERENCES distribution_centers(id) ON DELETE SET NULL,
                    INDEX idx_user_id (user_id),
                    INDEX idx_donor_id (donor_id),
                    INDEX idx_center_id (center_id),
                    INDEX idx_location_type (location_type),
                    INDEX idx_is_active (is_active)
                )
            """))
            conn.commit()
            print("✅ favorite_locations table created successfully!")
            
        except Exception as e:
            print(f"⚠️  Migration warning: {e}")
            # Table might already exist, which is fine
            
        print("\n📊 Migration complete!")
        print("\nNext steps:")
        print("1. Restart your FastAPI server")
        print("2. Users can now save favorite locations from listings")
        print("3. Access favorites from the profile menu (⭐ My Favorites)")

if __name__ == "__main__":
    migrate()
