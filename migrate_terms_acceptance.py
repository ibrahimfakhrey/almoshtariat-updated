#!/usr/bin/env python3
"""
Database migration script to add terms acceptance fields to User model
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from app_init import db
from models import User
from sqlalchemy import text

def create_app():
    """Create Flask app for migration"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///purchases.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your-secret-key-here'
    
    db.init_app(app)
    return app

def migrate_terms_acceptance():
    """Add terms acceptance columns to User table"""
    app = create_app()
    
    with app.app_context():
        try:
            # First, create all tables if they don't exist
            print("Creating database tables if they don't exist...")
            db.create_all()
            
            # Check if columns already exist
            with db.engine.connect() as conn:
                result = conn.execute(text("PRAGMA table_info(user)"))
                columns = [row[1] for row in result]
                
                if 'terms_accepted' not in columns:
                    print("Adding terms_accepted column...")
                    conn.execute(text("ALTER TABLE user ADD COLUMN terms_accepted BOOLEAN DEFAULT 0 NOT NULL"))
                    
                if 'terms_accepted_at' not in columns:
                    print("Adding terms_accepted_at column...")
                    conn.execute(text("ALTER TABLE user ADD COLUMN terms_accepted_at DATETIME"))
                    
                trans = conn.begin()
                trans.commit()
                
            print("Migration completed successfully!")
            
        except Exception as e:
            print(f"Migration failed: {e}")
            return False
            
    return True

if __name__ == '__main__':
    if migrate_terms_acceptance():
        print("Terms acceptance migration completed successfully!")
    else:
        print("Migration failed!")
        sys.exit(1)