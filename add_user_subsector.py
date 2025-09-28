#!/usr/bin/env python3
"""
Migration script to add subsector column to the User table
"""

import sqlite3
import os

def add_user_subsector_column():
    """Add subsector column to the User table"""
    
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
        
        # Check if subsector column already exists in user table
        cursor.execute("PRAGMA table_info(user)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'subsector' not in columns:
            # Add the subsector column to user table
            print("Adding subsector column to user table...")
            cursor.execute("ALTER TABLE user ADD COLUMN subsector VARCHAR(200)")
            
            # Commit the changes
            conn.commit()
            print("Successfully added subsector column to the User table.")
            
            # Verify the changes
            cursor.execute("PRAGMA table_info(user)")
            updated_columns = [column[1] for column in cursor.fetchall()]
            print(f"Updated user table columns: {updated_columns}")
            
            return True
        else:
            print("Subsector column already exists in user table.")
            return True
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print("Starting user subsector column migration...")
    success = add_user_subsector_column()
    if success:
        print("Migration completed successfully!")
        print("You can now restart your Flask application.")
    else:
        print("Migration failed!")