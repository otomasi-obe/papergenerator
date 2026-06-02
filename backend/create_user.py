#!/usr/bin/env python3
"""Create a test user for PaperFull"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import app
from database.models import db, User

def create_test_user(email, password, name):
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            print(f"User {email} already exists (ID: {existing.id})")
            return existing
        
        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Created user: {email} (ID: {user.id})")
        return user

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python create_user.py <email> <password> <name>")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    name = sys.argv[3]
    
    create_test_user(email, password, name)
