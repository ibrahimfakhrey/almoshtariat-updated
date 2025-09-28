#!/usr/bin/env python3

import sqlite3
import os

def add_document_columns():
    """Add electronic_bill_doc and owner_id_photo_doc columns to company table"""
    
    # Database path
    db_path = 'purchases.db'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False
    
    conn = None
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(company)")
        columns = [column[1] for column in cursor.fetchall()]
        
        columns_to_add = []
        if 'electronic_bill_doc' not in columns:
            columns_to_add.append('electronic_bill_doc')
        if 'owner_id_photo_doc' not in columns:
            columns_to_add.append('owner_id_photo_doc')
        
        if not columns_to_add:
            print("Columns already exist!")
            return True
        
        # Add the new columns
        for column in columns_to_add:
            print(f"Adding column: {column}")
            cursor.execute(f"ALTER TABLE company ADD COLUMN {column} VARCHAR(255)")
        
        # Commit changes
        conn.commit()
        print(f"Successfully added {len(columns_to_add)} column(s) to company table")
        
        # Verify columns were added
        cursor.execute("PRAGMA table_info(company)")
        new_columns = [column[1] for column in cursor.fetchall()]
        
        for column in columns_to_add:
            if column in new_columns:
                print(f"✓ Column {column} added successfully")
            else:
                print(f"✗ Failed to add column {column}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error adding columns: {e}")
        if conn is not None:
            conn.close()
        return False

if __name__ == '__main__':
    success = add_document_columns()
    if success:
        print("\nDatabase migration completed successfully!")
    else:
        print("\nDatabase migration failed!")