import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///hvac.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="tech", nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    notes = db.Column(db.Text)

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/")
@login_required
def dashboard():
    user = current_user()
    customers = Customer.query.order_by(Customer.id.desc()).all()
    return render_template("dashboard.html", user=user, customers=customers)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash("Logged in successfully.")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("login"))

@app.route("/customers/new", methods=["POST"])
@login_required
def add_customer():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    notes = request.form.get("notes", "").strip()

    if not first_name or not last_name:
        flash("First and last name are required.")
        return redirect(url_for("dashboard"))

    customer = Customer(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        notes=notes,
    )
    db.session.add(customer)
    db.session.commit()
    flash("Customer added.")
    return redirect(url_for("dashboard"))

def setup_app():
    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(email="admin@toucanhvac.local").first()
        if not admin:
            admin = User(
                name="Stephen Oldham",
                email="admin@toucanhvac.local",
                role="admin",
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

setup_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
