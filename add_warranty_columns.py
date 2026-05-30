from app import app, db
from sqlalchemy import text

columns = {
    "warranty_status": "VARCHAR(100)",
    "warranty_expiration": "VARCHAR(50)",
    "warranty_last_checked": "VARCHAR(50)",
    "warranty_notes": "TEXT",
}

with app.app_context():
    existing = [row[1] for row in db.session.execute(text("PRAGMA table_info(equipment)")).fetchall()]
    for name, sqltype in columns.items():
        if name not in existing:
            db.session.execute(text(f"ALTER TABLE equipment ADD COLUMN {name} {sqltype}"))
            print(f"Added column: {name}")
        else:
            print(f"Already exists: {name}")
    db.session.commit()
