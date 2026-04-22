import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "toucan-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///hvac.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="admin", nullable=False)

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

class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    unit_name = db.Column(db.String(120), nullable=False)
    heat_type = db.Column(db.String(50))
    filter_size = db.Column(db.String(50))
    model_number = db.Column(db.String(120))
    serial_number = db.Column(db.String(120))
    notes = db.Column(db.Text)

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)

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
def home():
    customer_count = Customer.query.count()
    property_count = Property.query.count()
    equipment_count = Equipment.query.count()
    recent_customers = Customer.query.order_by(Customer.id.desc()).limit(8).all()
    return render_template(
        "dashboard.html",
        user=current_user(),
        customer_count=customer_count,
        property_count=property_count,
        equipment_count=equipment_count,
        recent_customers=recent_customers
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash("Logged in successfully.")
            return redirect(url_for("home"))
        flash("Invalid email or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("login"))

@app.route("/customers")
@login_required
def customers():
    customer_list = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    return render_template("customers.html", user=current_user(), customers=customer_list)

@app.route("/customers/new", methods=["POST"])
@login_required
def create_customer():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip().lower()

    if not first_name or not last_name:
        flash("First and last name are required.")
        return redirect(url_for("customers"))

    customer = Customer(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email
    )
    db.session.add(customer)
    db.session.commit()
    flash("Customer created.")
    return redirect(url_for("customers"))

@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    properties = Property.query.filter_by(customer_id=customer.id).order_by(Property.id.desc()).all()
    return render_template("customer_detail.html", user=current_user(), customer=customer, properties=properties)

@app.route("/customers/<int:customer_id>/properties/new", methods=["GET", "POST"])
@login_required
def create_property(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        property_name = request.form.get("property_name", "").strip()
        address = request.form.get("address", "").strip()

        if not property_name or not address:
            flash("Property name and address are required.")
            return redirect(url_for("create_property", customer_id=customer.id))

        prop = Property(
            property_name=property_name,
            address=address,
            customer_id=customer.id
        )
        db.session.add(prop)
        db.session.commit()
        flash("Property added.")
        return redirect(url_for("customer_detail", customer_id=customer.id))

    return render_template("create_property.html", user=current_user(), customer=customer)

@app.route("/properties")
@login_required
def properties():
    property_list = Property.query.order_by(Property.id.desc()).all()
    rows = []
    for prop in property_list:
        customer = Customer.query.get(prop.customer_id)
        rows.append({"property": prop, "customer": customer})
    return render_template("properties.html", user=current_user(), rows=rows)

@app.route("/properties/<int:property_id>")
@login_required
def property_detail(property_id):
    prop = Property.query.get_or_404(property_id)
    customer = Customer.query.get_or_404(prop.customer_id)
    equipment_list = Equipment.query.filter_by(property_id=prop.id).order_by(Equipment.id.desc()).all()
    return render_template("property_detail.html", user=current_user(), property=prop, customer=customer, equipment_list=equipment_list)

@app.route("/properties/<int:property_id>/equipment/new", methods=["GET", "POST"])
@login_required
def create_equipment(property_id):
    prop = Property.query.get_or_404(property_id)
    customer = Customer.query.get_or_404(prop.customer_id)

    if request.method == "POST":
        unit_name = request.form.get("unit_name", "").strip()
        heat_type = request.form.get("heat_type", "").strip()
        filter_size = request.form.get("filter_size", "").strip()
        model_number = request.form.get("model_number", "").strip()
        serial_number = request.form.get("serial_number", "").strip()
        notes = request.form.get("notes", "").strip()

        if not unit_name:
            flash("Unit name is required.")
            return redirect(url_for("create_equipment", property_id=prop.id))

        item = Equipment(
            property_id=prop.id,
            unit_name=unit_name,
            heat_type=heat_type,
            filter_size=filter_size,
            model_number=model_number,
            serial_number=serial_number,
            notes=notes
        )
        db.session.add(item)
        db.session.commit()
        flash("Equipment added.")
        return redirect(url_for("property_detail", property_id=prop.id))

    return render_template("create_equipment.html", user=current_user(), property=prop, customer=customer)

@app.route("/equipment")
@login_required
def equipment():
    equipment_list = Equipment.query.order_by(Equipment.id.desc()).all()
    rows = []
    for item in equipment_list:
        prop = Property.query.get(item.property_id)
        customer = Customer.query.get(prop.customer_id) if prop else None
        rows.append({"equipment": item, "property": prop, "customer": customer})
    return render_template("equipment.html", user=current_user(), rows=rows)

def setup_app():
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(email="admin@toucanhvac.local").first()
        if not admin:
            admin = User(name="Stephen Oldham", email="admin@toucanhvac.local", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

setup_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
