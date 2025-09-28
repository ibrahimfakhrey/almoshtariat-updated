#!/usr/bin/env python3
"""
Migration script to add dual boolean column to the User table
"""

import sqlite3
import os
from datetime import datetime

def add_dual_column():
    """Add dual boolean column to the User table"""
    
    # Database path - adjust if needed
    db_path = 'purchases.db'
    
    # Check if database exists
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        # Try alternative paths
        alternative_paths = ['database.db', 'app.db', 'site.db']
        for alt_path in alternative_paths:
            if os.path.exists(alt_path):
                db_path = alt_path
                print(f"Found database at {alt_path}")
                break
        else:
            print("No database file found. Please check the database path.")
            return False
    
    conn = None
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(user)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'dual' in columns:
            print("✓ Column 'dual' already exists in the User table.")
            return True
        
        # Add the dual column
        print("Adding 'dual' boolean column to User table...")
        cursor.execute("ALTER TABLE user ADD COLUMN dual BOOLEAN DEFAULT 0 NOT NULL")
        
        # Update existing users with dual roles
        print("Updating existing users with dual roles...")
        cursor.execute("""
            UPDATE user 
            SET dual = 1 
            WHERE role = 'both' 
               OR (available_roles LIKE '%client%' AND available_roles LIKE '%company%')
        """)
        
        # Commit the changes
        conn.commit()
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(user)")
        updated_columns = [column[1] for column in cursor.fetchall()]
        
        if 'dual' in updated_columns:
            print("✅ Successfully added 'dual' column to User table.")
            
            # Show updated users count
            cursor.execute("SELECT COUNT(*) FROM user WHERE dual = 1")
            dual_users_count = cursor.fetchone()[0]
            print(f"✅ Updated {dual_users_count} users with dual roles.")
            
            return True
        else:
            print("❌ Failed to add 'dual' column.")
            return False
            
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def main():
    """Main function to run the migration"""
    print("=" * 50)
    print("User Table Migration: Adding 'dual' Column")
    print("=" * 50)
    
    success = add_dual_column()
    
    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed. Please check the errors above.")
    
    return success

if __name__ == '__main__':
    main()