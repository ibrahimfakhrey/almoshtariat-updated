#!/usr/bin/env python3

import os
import sys
from flask_app import app
from alembic.config import Config
from alembic import command

def generate_migration():
    with app.app_context():
        # Set up Alembic configuration
        alembic_cfg = Config('migrations/alembic.ini')
        
        # Generate migration
        command.revision(alembic_cfg, autogenerate=True, message="Add subsector column to company table")
        print("Migration generated successfully!")

if __name__ == '__main__':
    generate_migration()