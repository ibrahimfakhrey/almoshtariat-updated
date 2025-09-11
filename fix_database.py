#!/usr/bin/env python3
"""
Database migration script to add missing columns to User table
"""

import sqlite3
import os
from datetime import datetime

def fix_database():
    """Add missing columns to User table if they don't exist"""
    db_path = 'purchases.db'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get current table schema
        cursor.execute("PRAGMA table_info(user)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"Current User table columns: {columns}")
        
        # List of columns that should exist
        required_columns = {
            'is_verified': 'BOOLEAN DEFAULT 0 NOT NULL',
            'verification_code': 'VARCHAR(6)',
            'verification_sent_at': 'DATETIME'
        }
        
        # Add missing columns
        for column_name, column_def in required_columns.items():
            if column_name not in columns:
                try:
                    alter_sql = f"ALTER TABLE user ADD COLUMN {column_name} {column_def}"
                    print(f"Adding column: {alter_sql}")
                    cursor.execute(alter_sql)
                    print(f"✓ Added column {column_name}")
                except sqlite3.Error as e:
                    print(f"✗ Error adding column {column_name}: {e}")
            else:
                print(f"✓ Column {column_name} already exists")
        
        # Commit changes
        conn.commit()
        print("\n✓ Database migration completed successfully!")
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(user)")
        updated_columns = [column[1] for column in cursor.fetchall()]
        print(f"Updated User table columns: {updated_columns}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == '__main__':
    print("Starting database migration...")
    success = fix_database()
    if success:
        print("\n🎉 Migration completed! You can now test the username and email validation.")
    else:
        print("\n❌ Migration failed. Please check the errors above.")