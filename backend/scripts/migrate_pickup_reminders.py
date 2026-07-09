#!/usr/bin/env python3
"""
Migration script for Pickup Reminders feature
Adds pickup_reminders and reminder_settings tables
"""
import sys
import os

# Add parent directory to path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.app import engine
from sqlalchemy import text

def run_migration():
    """Execute the migration using the backend's database engine"""
    print("🔔 Starting Pickup Reminders Migration...")
    print(f"Using existing backend database connection")
    
    try:
        with engine.connect() as connection:
            # Start transaction
            trans = connection.begin()
            
            try:
                print("\n📊 Creating pickup_reminders table...")
                
                # Create pickup_reminders table
                try:
                    connection.execute(text("""
                        CREATE TABLE IF NOT EXISTS pickup_reminders (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            listing_id INT NOT NULL,
                            
                            scheduled_time DATETIME NOT NULL COMMENT 'When to send the reminder',
                            reminder_sent_at DATETIME NULL COMMENT 'When reminder was actually sent',
                            status ENUM(
                                'scheduled',
                                'sent',
                                'snoozed',
                                'completed',
                                'cancelled'
                            ) DEFAULT 'scheduled',
                            
                            sms_sent BOOLEAN DEFAULT FALSE,
                            email_sent BOOLEAN DEFAULT FALSE,
                            
                            snooze_count INT DEFAULT 0,
                            snoozed_until DATETIME NULL,
                            
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            FOREIGN KEY (listing_id) REFERENCES food_resources(id) ON DELETE CASCADE,
                            
                            INDEX idx_user (user_id),
                            INDEX idx_listing (listing_id),
                            INDEX idx_scheduled_time (scheduled_time),
                            INDEX idx_status (status)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                        COMMENT='Pickup reminder notifications for claimed food items'
                    """))
                    print("  ✅ Created pickup_reminders table")
                except Exception as e:
                    if "already exists" in str(e):
                        print("  ℹ️  pickup_reminders table already exists")
                    else:
                        raise
                
                print("\n📊 Creating reminder_settings table...")
                
                # Create reminder_settings table
                try:
                    connection.execute(text("""
                        CREATE TABLE IF NOT EXISTS reminder_settings (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL UNIQUE,
                            
                            enabled BOOLEAN DEFAULT TRUE,
                            advance_notice_hours FLOAT DEFAULT 2.0 COMMENT 'Hours before pickup to send reminder',
                            sms_enabled BOOLEAN DEFAULT TRUE,
                            email_enabled BOOLEAN DEFAULT FALSE,
                            auto_reminder BOOLEAN DEFAULT TRUE COMMENT 'Auto-schedule reminders on claim',
                            
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            
                            INDEX idx_user (user_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                        COMMENT='User preferences for pickup reminder notifications'
                    """))
                    print("  ✅ Created reminder_settings table")
                except Exception as e:
                    if "already exists" in str(e):
                        print("  ℹ️  reminder_settings table already exists")
                    else:
                        raise
                
                # Commit transaction
                trans.commit()
                
                print("\n✅ Migration completed successfully!")
                print("\n📋 Summary:")
                print("  • Created pickup_reminders table with status tracking")
                print("  • Created reminder_settings table for user preferences")
                print("  • Added indexes for efficient querying")
                print("  • Set up foreign key constraints")
                print("\n🎯 Pickup Reminders feature is now ready!")
                
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
