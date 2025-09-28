#!/usr/bin/env python3
"""
Script to add electronic_bill_doc and owner_id_photo_doc fields to Company table
"""

import sqlite3
import os
from flask import Flask
from app_init import db
from models import Company

def add_document_fields():
    """Add the new document fields to the Company table"""
    
    # Create Flask app context
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    with app.app_context():
        try:
            # Check if columns already exist
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('company')]
            
            if 'electronic_bill_doc' not in columns:
                print("Adding electronic_bill_doc column...")
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE company ADD COLUMN electronic_bill_doc VARCHAR(255)'))
                    conn.commit()
                print("✓ electronic_bill_doc column added successfully")
            else:
                print("electronic_bill_doc column already exists")
                
            if 'owner_id_photo_doc' not in columns:
                print("Adding owner_id_photo_doc column...")
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE company ADD COLUMN owner_id_photo_doc VARCHAR(255)'))
                    conn.commit()
                print("✓ owner_id_photo_doc column added successfully")
            else:
                print("owner_id_photo_doc column already exists")
                
            print("\nDatabase schema updated successfully!")
            
        except Exception as e:
            print(f"Error updating database: {e}")
            return False
            
    return True

if __name__ == '__main__':
    print("Adding document fields to Company table...")
    success = add_document_fields()
    if success:
        print("\nDocument fields added successfully!")
    else:
        print("\nFailed to add document fields.")