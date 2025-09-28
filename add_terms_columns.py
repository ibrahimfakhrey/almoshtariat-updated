#!/usr/bin/env python3
"""
Migration script to add terms_accepted and terms_accepted_at columns to the User table
"""

import sqlite3
import os
from datetime import datetime

def add_terms_columns():
    """Add terms_accepted and terms_accepted_at columns to the User table"""
    
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
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(user)")
        columns = [column[1] for column in cursor.fetchall()]
        
        columns_to_add = []
        if 'terms_accepted' not in columns:
            columns_to_add.append(('terms_accepted', "ALTER TABLE user ADD COLUMN terms_accepted BOOLEAN DEFAULT 0 NOT NULL"))
        
        if 'terms_accepted_at' not in columns:
            columns_to_add.append(('terms_accepted_at', "ALTER TABLE user ADD COLUMN terms_accepted_at DATETIME"))
        
        if not columns_to_add:
            print("Terms columns already exist in the database.")
            return True
        
        # Add the missing columns
        for column_name, sql in columns_to_add:
            print(f"Adding column: {column_name}")
            cursor.execute(sql)
        
        # Update existing users to have default values
        print("Updating existing users with default terms values...")
        cursor.execute("""
            UPDATE user 
            SET terms_accepted = 0
            WHERE terms_accepted IS NULL
        """)
        
        # Commit the changes
        conn.commit()
        print("Successfully added terms columns to the User table.")
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(user)")
        updated_columns = [column[1] for column in cursor.fetchall()]
        print(f"Updated columns: {updated_columns}")
        
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
    print("Starting terms columns migration...")
    success = add_terms_columns()
    if success:
        print("Migration completed successfully!")
        print("You can now restart your Flask application.")
    else:
        print("Migration failed!")