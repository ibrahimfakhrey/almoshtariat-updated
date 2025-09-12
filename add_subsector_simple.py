#!/usr/bin/env python3

import sqlite3

def add_subsector_column():
    # Connect to the database
    conn = sqlite3.connect('purchases.db')
    cursor = conn.cursor()
    
    try:
        # Check if subsector column already exists
        cursor.execute("PRAGMA table_info(company)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'subsector' not in columns:
            # Add the subsector column
            cursor.execute("ALTER TABLE company ADD COLUMN subsector VARCHAR(200)")
            conn.commit()
            print("Successfully added subsector column to company table")
        else:
            print("Subsector column already exists")
            
    except Exception as e:
        print(f"Error adding subsector column: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    add_subsector_column()