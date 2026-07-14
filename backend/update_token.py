import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from main import app, db
from utils.database.models import User

with app.app_context():
    user = User.query.filter_by(email="anabilhisyam24@gmail.com").first()
    if not user:
        print("User not found")
        sys.exit(1)
    print(f"Before: token_quota_monthly={user.token_quota_monthly}, token_used_month={user.token_used_month}")
    user.token_quota_monthly = user.token_quota_monthly + 500000
    db.session.commit()
    print(f"After: token_quota_monthly={user.token_quota_monthly}, token_used_month={user.token_used_month}")
