#!/usr/bin/env python3
from app_init import app, db
from models import User

with app.app_context():
    user = User.query.filter_by(username='karim').first()
    if user:
        print(f'User: {user.username}')
        print(f'Role: {user.role}')
        print(f'Active Role: {user.active_role}')
        print(f'Available Roles: {user.available_roles}')
        print(f'Dual Flag: {user.dual}')
        print(f'Has Dual Roles: {user.has_dual_roles}')
        print(f'Can Switch Roles: {user.can_switch_roles}')
    else:
        print('User karim not found')
        # Show all users
        users = User.query.all()
        for u in users:
            print(f'ID: {u.id}, Username: {u.username}, Role: {u.role}, Dual: {u.dual}')