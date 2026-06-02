#!/usr/bin/env python3
"""Reset password for a user"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import app
from database.models import db, User

def reset_password(email, new_password):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"User {email} not found")
            return False
        
        user.set_password(new_password)
        db.session.commit()
        print(f"Password reset for user: {email} (ID: {user.id})")
        return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python reset_password.py <email> <new_password>")
        sys.exit(1)
    
    email = sys.argv[1]
    new_password = sys.argv[2]
    
    reset_password(email, new_password)
