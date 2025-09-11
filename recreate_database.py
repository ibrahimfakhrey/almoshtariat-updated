#!/usr/bin/env python3
"""
Recreate database tables to fix SQLAlchemy schema caching issues
"""

import sqlite3
import os
from datetime import datetime

def backup_and_recreate_database():
    """Backup existing data and recreate tables with proper schema"""
    db_path = 'purchases.db'
    backup_path = f'purchases_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found!")
        return False
    
    conn = None
    try:
        # Create backup
        print(f"Creating backup: {backup_path}")
        os.system(f'cp {db_path} {backup_path}')
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get existing user data
        print("Backing up user data...")
        cursor.execute("SELECT * FROM user")
        users = cursor.fetchall()
        
        # Get column names for user table
        cursor.execute("PRAGMA table_info(user)")
        old_columns = [col[1] for col in cursor.fetchall()]
        print(f"Old columns: {old_columns}")
        
        # Drop and recreate user table with new schema
        print("Recreating user table...")
        cursor.execute("DROP TABLE IF EXISTS user_backup")
        cursor.execute("ALTER TABLE user RENAME TO user_backup")
        
        # Create new user table with complete schema
        create_user_table = """
        CREATE TABLE user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(80) NOT NULL UNIQUE,
            email VARCHAR(120) NOT NULL UNIQUE,
            password_hash VARCHAR(128) NOT NULL,
            role VARCHAR(20) NOT NULL,
            company_id INTEGER,
            name VARCHAR(100),
            country VARCHAR(100),
            city VARCHAR(100),
            phone_number VARCHAR(20),
            company_name VARCHAR(200),
            sector VARCHAR(100),
            tax_number VARCHAR(50),
            account_type VARCHAR(20),
            uploaded_file VARCHAR(255),
            is_verified BOOLEAN NOT NULL DEFAULT 0,
            verification_code VARCHAR(6),
            verification_sent_at DATETIME,
            FOREIGN KEY (company_id) REFERENCES company (id)
        )
        """
        
        cursor.execute(create_user_table)
        
        # Migrate data from backup table
        print("Migrating user data...")
        
        # Build insert statement based on available columns
        insert_columns = []
        select_columns = []
        
        new_columns = ['id', 'username', 'email', 'password_hash', 'role', 'company_id', 
                      'name', 'country', 'city', 'phone_number', 'company_name', 'sector', 
                      'tax_number', 'account_type', 'uploaded_file', 'is_verified', 
                      'verification_code', 'verification_sent_at']
        
        for col in new_columns:
            if col in old_columns:
                insert_columns.append(col)
                select_columns.append(col)
            elif col == 'is_verified':
                insert_columns.append(col)
                select_columns.append('0')  # Default value
            elif col in ['verification_code', 'verification_sent_at']:
                insert_columns.append(col)
                select_columns.append('NULL')  # Default NULL
        
        if insert_columns:
            insert_sql = f"""
            INSERT INTO user ({', '.join(insert_columns)})
            SELECT {', '.join(select_columns)}
            FROM user_backup
            """
            cursor.execute(insert_sql)
        
        # Drop backup table
        cursor.execute("DROP TABLE user_backup")
        
        # Commit changes
        conn.commit()
        
        # Verify new schema
        cursor.execute("PRAGMA table_info(user)")
        new_schema = cursor.fetchall()
        print("\nNew user table schema:")
        for col in new_schema:
            print(f"  {col[1]} {col[2]} {'NOT NULL' if col[3] else 'NULL'} {'DEFAULT ' + str(col[4]) if col[4] else ''}")
        
        # Count migrated records
        cursor.execute("SELECT COUNT(*) FROM user")
        count = cursor.fetchone()[0]
        print(f"\nMigrated {count} user records successfully.")
        
        conn.close()
        print("\n✅ Database recreation completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error recreating database: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

if __name__ == '__main__':
    print("Recreating database to fix SQLAlchemy schema issues...\n")
    success = backup_and_recreate_database()
    
    if success:
        print("\nDatabase recreation completed. Please restart the Flask server.")
    else:
        print("\nDatabase recreation failed. Check the error messages above.")