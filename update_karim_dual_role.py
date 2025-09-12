#!/usr/bin/env python3
"""
Script to update user 'karim' to have dual roles for testing role switching functionality.
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_init import app, db
from models import User

def update_karim_to_dual_role():
    """Update user karim to have dual roles"""
    with app.app_context():
        # Find user with username 'karim'
        user = User.query.filter_by(username='karim').first()
        
        if not user:
            print("User 'karim' not found. Let me show all users:")
            users = User.query.all()
            for u in users:
                print(f"ID: {u.id}, Username: {u.username}, Role: {u.role}, Active Role: {u.active_role}")
            return False
        
        print(f"Found user: {user.username}")
        print(f"Current role: {user.role}")
        print(f"Current active_role: {user.active_role}")
        print(f"Current available_roles: {user.available_roles}")
        
        # Update to dual role
        user.role = 'both'
        user.active_role = 'client'  # Start with client as active
        user.available_roles = 'client,company'  # Both roles available
        
        try:
            db.session.commit()
            print(f"\nSuccessfully updated user '{user.username}' to dual role!")
            print(f"New role: {user.role}")
            print(f"New active_role: {user.active_role}")
            print(f"New available_roles: {user.available_roles}")
            print(f"Has dual roles: {user.has_dual_roles}")
            print(f"Can switch roles: {user.can_switch_roles}")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error updating user: {e}")
            return False

if __name__ == '__main__':
    success = update_karim_to_dual_role()
    if success:
        print("\n✅ User 'karim' now has dual roles and can test the role switching functionality!")
    else:
        print("\n❌ Failed to update user 'karim'")