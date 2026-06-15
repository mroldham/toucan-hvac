import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app, db, User

if len(sys.argv) != 3:
    print("Usage: python3 scripts/reset_admin.py email password")
    sys.exit(1)

email = sys.argv[1].strip().lower()
password = sys.argv[2]

with app.app_context():
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(name="Stephen Oldham", email=email, role="admin")
        db.session.add(user)

    user.role = "admin"
    user.set_password(password)
    db.session.commit()

    print(f"Admin login reset for: {email}")
