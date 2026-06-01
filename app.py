import os
from datetime import datetime
from functools import wraps

from urllib.parse import quote_plus
from geopy.geocoders import Nominatim
import sqlite3
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS


app = Flask(__name__)

geolocator = Nominatim(user_agent="toucan_hvac")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "toucan-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///hvac.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

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
    mailing_address = db.Column(db.String(255))
    birthday = db.Column(db.String(20))


class CustomerPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)

class MonitoringDevice(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=True)

    device_name = db.Column(db.String(100), nullable=False, default="Toucan Monitor")
    device_uid = db.Column(db.String(100), unique=True, nullable=False)
    api_key = db.Column(db.String(100), nullable=True)

    firmware_version = db.Column(db.String(50), nullable=True)
    last_seen = db.Column(db.DateTime, nullable=True)

    notes = db.Column(db.Text, nullable=True)


class SensorReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(db.Integer, db.ForeignKey("monitoring_device.id"), nullable=False)

    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    supply_temp = db.Column(db.Float, nullable=True)
    return_temp = db.Column(db.Float, nullable=True)
    attic_temp = db.Column(db.Float, nullable=True)
    humidity = db.Column(db.Float, nullable=True)

    temp_split = db.Column(db.Float, nullable=True)

    overflow_alert = db.Column(db.Boolean, default=False)
    system_running = db.Column(db.Boolean, default=False)

    raw_json = db.Column(db.Text, nullable=True)

class PropertyPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    unit_name = db.Column(db.String(120), nullable=False)
    heat_type = db.Column(db.String(50))
    filter_size = db.Column(db.String(50))
    model_number = db.Column(db.String(120))
    serial_number = db.Column(db.String(120))
    notes = db.Column(db.Text)

    furnace_model = db.Column(db.String(120))
    furnace_serial = db.Column(db.String(120))
    evaporator_model = db.Column(db.String(120))
    evaporator_serial = db.Column(db.String(120))
    condenser_model = db.Column(db.String(120))
    condenser_serial = db.Column(db.String(120))
    air_handler_model = db.Column(db.String(120))
    air_handler_serial = db.Column(db.String(120))

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

class ServiceJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))

    description = db.Column(db.Text)
    scheduled_date = db.Column(db.String(50))
    status = db.Column(db.String(50), default="Scheduled")
    priority = db.Column(db.String(50), default="Normal")

    technician = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class PriceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_name = db.Column(db.String(200))
    category = db.Column(db.String(100))
    price = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)

class FilterProduct(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    size = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(200))
    price = db.Column(db.Float, nullable=False, default=0.0)
    active = db.Column(db.Boolean, default=True)


class FilterOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(150))
    address = db.Column(db.String(255))
    filter_size = db.Column(db.String(80))
    quantity = db.Column(db.String(50))
    frequency = db.Column(db.String(80))
    notes = db.Column(db.Text)


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)



def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user.role != "admin":
            flash("Access denied")
            return redirect("/my-jobs")
        return f(*args, **kwargs)
    return wrapper

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def _convert_to_degrees(value):
    try:
        d = value[0][0] / value[0][1]
        m = value[1][0] / value[1][1]
        s = value[2][0] / value[2][1]
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        try:
            d = float(value[0])
            m = float(value[1])
            s = float(value[2])
            return d + (m / 60.0) + (s / 3600.0)
        except Exception:
            return None


def extract_gps_coordinates(filepath):
    try:
        image = Image.open(filepath)
        exifdata = image.getexif()
        if not exifdata:
            return None, None

        gps_info = {}
        for tag_id, value in exifdata.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for key in value.keys():
                    decoded = GPSTAGS.get(key, key)
                    gps_info[decoded] = value[key]

        if not gps_info:
            return None, None

        lat = gps_info.get("GPSLatitude")
        lat_ref = gps_info.get("GPSLatitudeRef")
        lon = gps_info.get("GPSLongitude")
        lon_ref = gps_info.get("GPSLongitudeRef")

        if not lat or not lat_ref or not lon or not lon_ref:
            return None, None

        latitude = _convert_to_degrees(lat)
        longitude = _convert_to_degrees(lon)

        if latitude is None or longitude is None:
            return None, None

        if lat_ref in ["S", b"S"]:
            latitude = -latitude
        if lon_ref in ["W", b"W"]:
            longitude = -longitude

        return latitude, longitude
    except Exception:
        return None, None


def save_uploaded_photo(file_storage, prefix):
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    filename = secure_filename(f"{prefix}_{timestamp}.{ext}")
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(filepath)
    latitude, longitude = extract_gps_coordinates(filepath)
    return filename, latitude, longitude



def google_geocode_address(address):
    import os
    import requests

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY") or "AIzaSyAXWVwu7HbOrOSeol7FzneHmUpah1iMg6g"

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}

    r = requests.get(url, params=params, timeout=15)
    data = r.json()

    if data.get("status") == "OK" and data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]

    raise RuntimeError(data.get("status", "Google geocode failed"))


@app.route("/")
def public_root_home():
    return render_template("public_home.html")

@app.route("/dashboard")
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


@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    customer_list = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    photo_counts = {
        row.customer_id: row.count
        for row in db.session.query(
            CustomerPhoto.customer_id,
            db.func.count(CustomerPhoto.id).label("count")
        ).group_by(CustomerPhoto.customer_id).all()
    }
    return render_template(
        "customers.html",
        user=current_user(),
        customers=customer_list,
        customer_list=customer_list,
        photo_counts=photo_counts
    )


@app.route("/customers/new", methods=["POST"])
@login_required
def create_customer():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip().lower()
    mailing_address = request.form.get("mailing_address", "").strip()
    birthday = request.form.get("birthday", "").strip()

    if not first_name or not last_name:
        flash("First and last name are required.")
        return redirect(url_for("customers"))

    customer = Customer(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        mailing_address=mailing_address,
        birthday=birthday
    )
    db.session.add(customer)
    db.session.commit()
    flash("Customer created.")
    return redirect(url_for("customers"))

    customer = Customer(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        mailing_address=mailing_address,
        birthday=birthday
    )
    db.session.add(customer)
    db.session.commit()
    flash("Customer created.")
    return redirect(url_for("customers"))

@app.route('/service-jobs')
def service_jobs():
    jobs = ServiceJob.query.all()
    customers = {c.id: c for c in Customer.query.all()}
    properties = {p.id: p for p in Property.query.all()}
    return render_template(
        'service_jobs.html',
        jobs=jobs,
        customers=customers,
        properties=properties,
        equipment_by_property={},
        user=current_user()
    )


@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    properties = Property.query.filter_by(customer_id=customer.id).order_by(Property.id.desc()).all()

    equipment_by_property = {}
    for prop in properties:
        equipment_by_property[prop.id] = Equipment.query.filter_by(property_id=prop.id).order_by(Equipment.id.desc()).all()

    photos = CustomerPhoto.query.filter_by(customer_id=customer.id).order_by(CustomerPhoto.id.desc()).all()

    return render_template(
        "customer_detail.html",
        user=current_user(),
        customer=customer,
        properties=properties,
        equipment_by_property={},
        photos=photos
    )

@app.route("/customers/<int:customer_id>/photos/upload", methods=["POST"])
@login_required
def upload_customer_photos(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    files = request.files.getlist("photos")
    caption = request.form.get("caption", "").strip()

    valid_files = [f for f in files if f and f.filename]
    if not valid_files:
        flash("Please choose at least one photo.")
        return redirect(url_for("customer_detail", customer_id=customer.id))

    uploaded = 0
    for photo in valid_files:
        if not allowed_file(photo.filename):
            continue

        filename, latitude, longitude = save_uploaded_photo(photo, f"customer_{customer.id}")
        record = CustomerPhoto(
            customer_id=customer.id,
            filename=filename,
            caption=caption,
            latitude=latitude,
            longitude=longitude
        )
        db.session.add(record)
        uploaded += 1

    db.session.commit()

    if uploaded:
        flash(f"{uploaded} customer photo(s) uploaded.")
    else:
        flash("No allowed photo files were uploaded.")

    return redirect(url_for("customer_detail", customer_id=customer.id))


@app.route("/customer-photos/<int:photo_id>")
@login_required
def customer_photo_view(photo_id):
    photo = CustomerPhoto.query.get_or_404(photo_id)
    customer = Customer.query.get_or_404(photo.customer_id)
    return render_template(
        "photo_view.html",
        user=current_user(),
        photo_url=url_for("static", filename="uploads/" + photo.filename),
        title=f"{customer.first_name} {customer.last_name} photo",
        caption=photo.caption,
        latitude=photo.latitude,
        longitude=photo.longitude,
        back_url=url_for("customer_detail", customer_id=customer.id)
    )


@app.route("/customer-photos/<int:photo_id>/delete", methods=["POST"])
@login_required
def delete_customer_photo(photo_id):
    photo = CustomerPhoto.query.get_or_404(photo_id)
    customer_id = photo.customer_id
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], photo.filename)

    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass

    db.session.delete(photo)
    db.session.commit()
    flash("Customer photo deleted.")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/customers/<int:customer_id>/add-property", methods=["GET", "POST"])
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
@admin_required
@login_required
def properties():
    props = Property.query.order_by(Property.id.desc()).all()
    return render_template("properties.html", properties=props)


@app.route("/properties/<int:property_id>")
@login_required
def property_detail(property_id):
    prop = Property.query.get_or_404(property_id)
    customer = Customer.query.get(prop.customer_id) if prop.customer_id else None

    equipment = Equipment.query.filter_by(property_id=prop.id).order_by(Equipment.id.desc()).all()
    equipment_list = equipment

    photos = PropertyPhoto.query.filter_by(property_id=prop.id).order_by(PropertyPhoto.id.desc()).all()

    return render_template(
        "property_detail.html",
        user=current_user(),
        property=prop,
        prop=prop,
        customer=customer,
        equipment=equipment,
        equipment_list=equipment_list,
        photos=photos
    )

@app.route("/properties/<int:property_id>/photos/upload", methods=["POST"])
@login_required
def upload_property_photos(property_id):
    prop = Property.query.get_or_404(property_id)
    files = request.files.getlist("photos")
    caption = request.form.get("caption", "").strip()

    valid_files = [f for f in files if f and f.filename]
    if not valid_files:
        flash("Please choose at least one photo.")
        return redirect(url_for("property_detail", property_id=prop.id))

    uploaded = 0
    for photo in valid_files:
        if not allowed_file(photo.filename):
            continue

        filename, latitude, longitude = save_uploaded_photo(photo, f"property_{prop.id}")
        record = PropertyPhoto(
            property_id=prop.id,
            filename=filename,
            caption=caption,
            latitude=latitude,
            longitude=longitude
        )
        db.session.add(record)
        uploaded += 1

    db.session.commit()

    if uploaded:
        flash(f"{uploaded} property photo(s) uploaded.")
    else:
        flash("No allowed photo files were uploaded.")

    return redirect(url_for("property_detail", property_id=prop.id))


@app.route("/property-photos/<int:photo_id>")
@login_required
def property_photo_view(photo_id):
    photo = PropertyPhoto.query.get_or_404(photo_id)
    prop = Property.query.get_or_404(photo.property_id)
    customer = Customer.query.get_or_404(prop.customer_id)
    return render_template(
        "photo_view.html",
        user=current_user(),
        photo_url=url_for("static", filename="uploads/" + photo.filename),
        title=f"{prop.property_name} photo",
        caption=photo.caption,
        latitude=photo.latitude,
        longitude=photo.longitude,
        back_url=url_for("property_detail", property_id=prop.id),
        subtitle=f"{customer.first_name} {customer.last_name} • {prop.address}"
    )


@app.route("/property-photos/<int:photo_id>/delete", methods=["POST"])
@login_required
def delete_property_photo(photo_id):
    photo = PropertyPhoto.query.get_or_404(photo_id)
    property_id = photo.property_id
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], photo.filename)

    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass

    db.session.delete(photo)
    db.session.commit()
    flash("Property photo deleted.")
    return redirect(url_for("property_detail", property_id=property_id))


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

    return render_template(
        "create_equipment.html",
        user=current_user(),
        property=prop,
        customer=customer
    )


@app.route("/equipment")
@admin_required
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
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        db.create_all()

        admin = User.query.filter_by(email="admin@toucanhvac.local").first()
        if not admin:
            admin = User(
                name="Stephen Oldham",
                email="admin@toucanhvac.local",
                role="admin"
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()


setup_app()


@app.route("/filter-order", methods=["GET", "POST"])
def filter_order():
    db.create_all()

    if request.method == "POST":
        order = FilterOrder(
            name=request.form.get("name"),
            phone=request.form.get("phone"),
            email=request.form.get("email"),
            address=request.form.get("address"),
            filter_size=request.form.get("filter_size"),
            quantity=request.form.get("quantity"),
            frequency=request.form.get("frequency"),
            notes=request.form.get("notes"),
        )
        db.session.add(order)
        db.session.commit()
        flash("Filter order submitted.")
        return redirect(url_for("filter_order"))

    products = FilterProduct.query.filter_by(active=True).order_by(FilterProduct.size.asc()).all()
    return render_template("filter_order.html", products=products)


@app.route("/filter-orders")
@login_required
def filter_orders():
    db.create_all()
    orders = FilterOrder.query.order_by(FilterOrder.id.desc()).all()
    return render_template("filter_orders.html", orders=orders)



@app.route("/filter-products", methods=["GET", "POST"])
@login_required
def filter_products():
    db.create_all()

    if request.method == "POST":
        product = FilterProduct(
            size=request.form.get("size"),
            description=request.form.get("description"),
            price=float(request.form.get("price") or 0),
            active=True
        )
        db.session.add(product)
        db.session.commit()
        flash("Filter product added.")
        return redirect(url_for("filter_products"))

    products = FilterProduct.query.order_by(FilterProduct.size.asc()).all()
    return render_template("filter_products.html", products=products)


@app.route("/filter-products/<int:product_id>/edit", methods=["POST"])
@login_required
def edit_filter_product(product_id):
    product = FilterProduct.query.get_or_404(product_id)
    product.size = request.form.get("size")
    product.description = request.form.get("description")
    product.price = float(request.form.get("price") or 0)
    product.active = True if request.form.get("active") == "on" else False
    db.session.commit()
    flash("Filter product updated.")
    return redirect(url_for("filter_products"))




# ===== CUSTOMER EDIT =====
@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        customer.first_name = request.form.get("first_name", "").strip()
        customer.last_name = request.form.get("last_name", "").strip()
        customer.phone = request.form.get("phone", "").strip()
        customer.email = request.form.get("email", "").strip()
        customer.mailing_address = request.form.get("mailing_address", "").strip()
        customer.birthday = request.form.get("birthday", "").strip()

        db.session.commit()
        flash("Customer updated.")
        return redirect(url_for("customer_detail", customer_id=customer.id))

    return render_template("edit_customer.html", customer=customer)


# ===== CUSTOMER DELETE =====
@app.route("/customers/<int:customer_id>/delete")
@login_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    flash("Customer deleted.")
    return redirect(url_for("customers"))


# ===== PROPERTY DELETE =====
@app.route("/properties/<int:property_id>/delete")
@login_required
def delete_property(property_id):
    prop = Property.query.get_or_404(property_id)
    db.session.delete(prop)
    db.session.commit()
    flash("Property deleted.")
    return redirect(url_for("properties"))


# ===== EQUIPMENT DELETE =====
@app.route("/equipment/<int:equipment_id>/delete")
@login_required
def delete_equipment(equipment_id):
    eq = Equipment.query.get_or_404(equipment_id)
    db.session.delete(eq)
    db.session.commit()
    flash("Equipment deleted.")
    return redirect(url_for("equipment"))


# ===== EQUIPMENT REPLACE =====
@app.route("/equipment/<int:equipment_id>/replace", methods=["POST"])
@login_required
def replace_equipment(equipment_id):
    eq = Equipment.query.get_or_404(equipment_id)

    # mark old equipment as inactive
    if hasattr(eq, "active"):
        eq.active = False

    # create new equipment
    new_eq = Equipment(
        property_id=eq.property_id,
        equipment_type=request.form.get("equipment_type"),
        model=request.form.get("model"),
        serial=request.form.get("serial"),
        notes="Replaced old unit ID " + str(eq.id)
    )

    db.session.add(new_eq)
    db.session.commit()

    flash("Equipment replaced successfully.")
    return redirect(url_for("property_detail", property_id=eq.property_id))




# ===== CLEAN EQUIPMENT UI ROUTES =====
@app.route("/ui/properties/<int:property_id>/equipment/add", methods=["GET", "POST"])
@login_required
def ui_add_equipment(property_id):
    property = Property.query.get_or_404(property_id)

    if request.method == "POST":
        eq = Equipment(
            property_id=property.id,
            unit_name=request.form.get("unit_name") or "HVAC Unit",
            heat_type=request.form.get("heat_type"),
            filter_size=request.form.get("filter_size"),
            model_number=request.form.get("condenser_model") or request.form.get("furnace_model") or request.form.get("air_handler_model"),
            serial_number=request.form.get("condenser_serial") or request.form.get("furnace_serial") or request.form.get("air_handler_serial"),
            furnace_model=request.form.get("furnace_model"),
            furnace_serial=request.form.get("furnace_serial"),
            evaporator_model=request.form.get("evaporator_model"),
            evaporator_serial=request.form.get("evaporator_serial"),
            condenser_model=request.form.get("condenser_model"),
            condenser_serial=request.form.get("condenser_serial"),
            air_handler_model=request.form.get("air_handler_model"),
            air_handler_serial=request.form.get("air_handler_serial"),
            notes=request.form.get("notes")
        )

        db.session.add(eq)
        db.session.commit()
        flash("Equipment added.")
        return redirect(url_for("property_detail", property_id=property.id))

    return render_template("ui_equipment_form.html", property=property, equipment=None, title="Add Equipment")


@app.route("/ui/equipment/<int:equipment_id>/edit", methods=["GET", "POST"])
@login_required
def ui_edit_equipment(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    property = Property.query.get_or_404(equipment.property_id)

    if request.method == "POST":
        equipment.unit_name = request.form.get("unit_name") or "HVAC Unit"
        equipment.heat_type = request.form.get("heat_type")
        equipment.filter_size = request.form.get("filter_size")
        equipment.furnace_model = request.form.get("furnace_model")
        equipment.furnace_serial = request.form.get("furnace_serial")
        equipment.evaporator_model = request.form.get("evaporator_model")
        equipment.evaporator_serial = request.form.get("evaporator_serial")
        equipment.condenser_model = request.form.get("condenser_model")
        equipment.condenser_serial = request.form.get("condenser_serial")
        equipment.air_handler_model = request.form.get("air_handler_model")
        equipment.air_handler_serial = request.form.get("air_handler_serial")
        equipment.model_number = request.form.get("condenser_model") or request.form.get("furnace_model") or request.form.get("air_handler_model")
        equipment.serial_number = request.form.get("condenser_serial") or request.form.get("furnace_serial") or request.form.get("air_handler_serial")
        equipment.notes = request.form.get("notes")

        db.session.commit()
        flash("Equipment updated.")
        return redirect(url_for("property_detail", property_id=equipment.property_id))

    return render_template("ui_equipment_form.html", property=property, equipment=equipment, title="Edit Equipment")


@app.route("/ui/equipment/<int:equipment_id>/archive")
@login_required
def ui_archive_equipment(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)

    if hasattr(equipment, "active"):
        equipment.active = False
    elif hasattr(equipment, "notes"):
        old_notes = equipment.notes or ""
        if "[ARCHIVED]" not in old_notes:
            equipment.notes = "[ARCHIVED] " + old_notes

    db.session.commit()
    flash("Equipment archived.")
    return redirect(url_for("property_detail", property_id=equipment.property_id))






@app.route("/service-jobs/new", methods=["GET", "POST"])
@login_required
def new_service_job():
    db.create_all()

    if request.method == "POST":
        job = ServiceJob(
            customer_id=request.form.get("customer_id") or None,
            property_id=request.form.get("property_id") or None,
            description=request.form.get("description"),
            scheduled_date=request.form.get("scheduled_date"),
            status=request.form.get("status") or "Scheduled",
            priority=request.form.get("priority") or "Normal",
            technician=request.form.get("technician")
        )
        db.session.add(job)
        db.session.commit()
        flash("Service job added.")
        return redirect(url_for("service_jobs"))

    customers = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    properties = Property.query.order_by(Property.property_name.asc()).all()
    technicians = User.query.order_by(User.name.asc()).all()

    return render_template(
        "service_job_form.html",
        customers=customers,
        properties=properties,
        technicians=technicians
    )



@app.route("/calendar")
@login_required
def calendar_view():
    jobs = ServiceJob.query.all()
    return render_template("calendar.html", jobs=jobs)


@app.route("/service-jobs/<int:job_id>")
@login_required
def service_job_detail(job_id):
    job = ServiceJob.query.get_or_404(job_id)
    customer = Customer.query.get(job.customer_id) if job.customer_id else None
    property = Property.query.get(job.property_id) if job.property_id else None
    photos = ServiceJobPhoto.query.filter_by(job_id=job.id).order_by(ServiceJobPhoto.id.desc()).all()
    return render_template("service_job_detail.html", job=job, customer=customer, property=property, photos=photos)




@app.route("/service-jobs/<int:job_id>/edit", methods=["GET", "POST"])
@login_required
def edit_service_job(job_id):
    job = ServiceJob.query.get_or_404(job_id)

    if request.method == "POST":
        job.customer_id = request.form.get("customer_id") or None
        job.property_id = request.form.get("property_id") or None
        job.technician = request.form.get("technician")
        job.description = request.form.get("description")
        job.scheduled_date = request.form.get("scheduled_date")
        job.status = request.form.get("status")
        job.priority = request.form.get("priority") or "Normal"
        if hasattr(job, "notes"):
            job.notes = request.form.get("notes")
        if hasattr(job, "work_performed"):
            job.work_performed = request.form.get("work_performed")

        db.session.commit()
        flash("Job updated.")
        return redirect(url_for("service_job_detail", job_id=job.id))

    customers = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    properties = Property.query.order_by(Property.property_name.asc()).all()
    technicians = User.query.order_by(User.name.asc()).all()

    return render_template(
        "edit_service_job.html",
        job=job,
        customers=customers,
        properties=properties,
        technicians=technicians,
        user=current_user()
    )

@app.route("/service-jobs/<int:job_id>/update", methods=["POST"])
@login_required
def update_service_job(job_id):
    job = ServiceJob.query.get_or_404(job_id)
    job.status = request.form.get("status")
    job.technician = request.form.get("technician")
    if hasattr(job, "work_performed"):
        job.work_performed = request.form.get("work_performed")
    db.session.commit()
    flash("Job updated.")
    return redirect(url_for("service_job_detail", job_id=job.id))

@app.route("/tech-mobile")
@login_required
def tech_mobile():
    user = current_user()

    if user.role == "admin":
        jobs = ServiceJob.query.order_by(ServiceJob.scheduled_date.asc()).all()
    else:
        jobs = ServiceJob.query.filter_by(
            technician=user.name
        ).order_by(ServiceJob.scheduled_date.asc()).all()

    customers = {c.id: c for c in Customer.query.all()}
    properties = {p.id: p for p in Property.query.all()}

    return render_template(
        "tech_mobile.html",
        jobs=jobs,
        customers=customers,
        properties=properties,
        user=user,
        current_user=current_user
    )

@app.route("/my-jobs")
@login_required
def my_jobs():
    user = current_user()
    jobs = ServiceJob.query.filter_by(technician=user.name).all()

    customers = {c.id: c for c in Customer.query.all()}
    properties = {p.id: p for p in Property.query.all()}

    equipment_by_property = {}
    for e in Equipment.query.all():
        equipment_by_property.setdefault(e.property_id, []).append(e)

    return render_template(
        "my_jobs.html",
        jobs=jobs,
        customers=customers,
        properties=properties,
        equipment_by_property=equipment_by_property,
        user=user,
        current_user=user
    )






@app.route("/equipment/<int:equipment_id>")
@login_required
def equipment_detail(equipment_id):
    unit = Equipment.query.get_or_404(equipment_id)
    prop = Property.query.get(unit.property_id) if unit.property_id else None
    customer = Customer.query.get(prop.customer_id) if prop and prop.customer_id else None
    return render_template(
        "equipment_detail.html",
        unit=unit,
        equipment=unit,
        property=prop,
        prop=prop,
        customer=customer,
        user=current_user(),
        current_user=current_user()
    )


@app.route("/field")
@login_required
def field_dashboard():
    user = current_user()

    if getattr(user, "role", "") == "admin":
        jobs = ServiceJob.query.order_by(ServiceJob.id.desc()).all()
    else:
        jobs = ServiceJob.query.filter_by(technician=user.name).order_by(ServiceJob.id.desc()).all()

    def job_priority(job):
        status = (job.status or "Open").lower()
        date_text = str(getattr(job, "scheduled_date", "") or getattr(job, "date", "") or "")

        if status in ["completed", "billed", "closed"]:
            status_rank = 3
        elif "progress" in status:
            status_rank = 1
        else:
            status_rank = 2

        return (status_rank, date_text, -job.id)

    jobs = sorted(jobs, key=job_priority)

    customers = {c.id: c for c in Customer.query.all()}
    properties = {p.id: p for p in Property.query.all()}

    equipment_by_property = {}
    for e in Equipment.query.all():
        equipment_by_property.setdefault(e.property_id, []).append(e)

    return render_template(
        "field.html",
        jobs=jobs,
        customers=customers,
        properties=properties,
        equipment_by_property=equipment_by_property,
        user=user,
        current_user=user
    )


@app.route("/jobs/<int:job_id>/quick-update", methods=["POST"])
@login_required
def quick_update_job(job_id):
    job = ServiceJob.query.get_or_404(job_id)

    status = request.form.get("status")
    note = request.form.get("note")

    if status:
        job.status = status

    if note:
        if hasattr(job, "description"):
            old_text = job.description or ""
            job.description = (old_text + "\n\nField note: " + note).strip()
        else:
            print("FIELD NOTE:", note)

    file = request.files.get("photo")
    if file and file.filename:
        upload_dir = os.path.join(app.root_path, "static", "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        filename = "job_" + str(job.id) + "_" + secure_filename(file.filename)
        file.save(os.path.join(upload_dir, filename))

        try:
            photo = ServiceJobPhoto(
                job_id=job.id,
                filename=filename,
                caption=note or "Field photo"
            )
            db.session.add(photo)
        except Exception as e:
            print("Photo record skipped:", e)

    db.session.commit()
    flash("Job updated.")
    return redirect(url_for("field_dashboard"))


class ServiceJobPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("service_job.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255))


@app.route("/service-jobs/<int:job_id>/photos", methods=["POST"])
@login_required
def add_service_job_photo(job_id):
    db.create_all()
    job = ServiceJob.query.get_or_404(job_id)

    file = request.files.get("photo")
    caption = request.form.get("caption")

    if file and file.filename:
        upload_dir = os.path.join(app.root_path, "static", "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        filename = "job_" + str(job.id) + "_" + secure_filename(file.filename)
        file.save(os.path.join(upload_dir, filename))

        photo = ServiceJobPhoto(
            job_id=job.id,
            filename=filename,
            caption=caption
        )
        db.session.add(photo)
        db.session.commit()
        flash("Job photo uploaded.")

    return redirect(url_for("service_job_detail", job_id=job.id))


class ToucanInvoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"))
    job_id = db.Column(db.Integer)
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.String(30))
    status = db.Column(db.String(50), default="Draft")
    notes = db.Column(db.Text)
    subtotal = db.Column(db.Float, default=0)
    tax = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)




class PartsPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, default=0)
    notes = db.Column(db.String(255))




def generate_invoice_number():
    last_invoice = (
        ToucanInvoice.query
        .order_by(ToucanInvoice.id.desc())
        .first()
    )

    if last_invoice and last_invoice.invoice_number:
        try:
            return str(int(last_invoice.invoice_number) + 1)
        except:
            pass

    return "9269"


class ToucanInvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("toucan_invoice.id"))
    description = db.Column(db.String(255))
    quantity = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    line_total = db.Column(db.Float, default=0)



@app.route("/invoice-center")
@login_required
def invoice_center():
    db.create_all()
    invoices = ToucanInvoice.query.order_by(ToucanInvoice.id.desc()).all()
    customers = {c.id: c for c in Customer.query.all()}
    properties = {p.id: p for p in Property.query.all()}
    return render_template("invoice_center.html", invoices=invoices, customers=customers, properties=properties)


@app.route("/invoice-center/new", methods=["GET", "POST"])
@login_required
def new_toucan_invoice():
    db.create_all()

    if request.method == "POST":
        invoice = ToucanInvoice(
            customer_id=request.form.get("customer_id") or None,
            property_id=request.form.get("property_id") or None,
            invoice_number=generate_invoice_number(),
            invoice_date=request.form.get("invoice_date"),
            status=request.form.get("status") or "Draft",
            notes=request.form.get("notes")
        )
        db.session.add(invoice)
        db.session.commit()

        subtotal = 0

        descriptions = request.form.getlist("description[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("unit_price[]")

        for desc, qty, price in zip(descriptions, quantities, prices):
            if not desc.strip():
                continue

            q = float(qty or 0)
            p = float(price or 0)
            line_total = q * p
            subtotal += line_total

            item = ToucanInvoiceItem(
                invoice_id=invoice.id,
                description=desc,
                quantity=q,
                unit_price=p,
                line_total=line_total
            )
            db.session.add(item)

        tax_rate = float(request.form.get("tax_rate") or 0)
        tax = subtotal * (tax_rate / 100)
        total = subtotal + tax

        invoice.subtotal = subtotal
        invoice.tax = tax
        invoice.total = total

        db.session.commit()
        flash("Invoice created.")
        return redirect(url_for("toucan_invoice_detail", invoice_id=invoice.id))

    customers = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    properties = Property.query.order_by(Property.property_name.asc()).all()
    return render_template("new_toucan_invoice.html", customers=customers, properties=properties, job=None)


@app.route("/invoice-center/from-job/<int:job_id>", methods=["GET", "POST"])
@login_required
def invoice_from_job(job_id):
    job = ServiceJob.query.get_or_404(job_id)
    customer = Customer.query.get(job.customer_id) if job.customer_id else None
    property = Property.query.get(job.property_id) if job.property_id else None

    if request.method == "POST":
        invoice = ToucanInvoice(
            customer_id=request.form.get("customer_id") or job.customer_id or None,
            property_id=request.form.get("property_id") or job.property_id or None,
            job_id=job.id,
            invoice_number=generate_invoice_number(),
            invoice_date=request.form.get("invoice_date"),
            status=request.form.get("status") or "Draft",
            notes=request.form.get("notes")
        )
        db.session.add(invoice)
        db.session.commit()

        subtotal = 0
        descriptions = request.form.getlist("description[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("unit_price[]")

        for desc, qty, price in zip(descriptions, quantities, prices):
            if not desc.strip():
                continue

            q = float(qty or 0)
            p = float(price or 0)
            line_total = q * p
            subtotal += line_total

            item = ToucanInvoiceItem(
                invoice_id=invoice.id,
                description=desc,
                quantity=q,
                unit_price=p,
                line_total=line_total
            )
            db.session.add(item)

        tax_rate = float(request.form.get("tax_rate") or 0)
        tax = subtotal * (tax_rate / 100)

        invoice.subtotal = subtotal
        invoice.tax = tax
        invoice.total = subtotal + tax

        # Mark job billed after invoice is created
        job.status = "Billed"

        db.session.commit()
        flash("Invoice created from job.")
        return redirect(url_for("toucan_invoice_detail", invoice_id=invoice.id))

    customers = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    properties = Property.query.order_by(Property.property_name.asc()).all()

    return render_template(
        "new_toucan_invoice.html",
        customers=customers,
        properties=properties,
        job=job,
        customer=customer,
        property=property
    )

@app.route("/invoice-center/<int:invoice_id>")
@login_required
def toucan_invoice_detail(invoice_id):
    invoice = ToucanInvoice.query.get_or_404(invoice_id)
    items = ToucanInvoiceItem.query.filter_by(invoice_id=invoice.id).all()
    customer = Customer.query.get(invoice.customer_id) if invoice.customer_id else None
    property = Property.query.get(invoice.property_id) if invoice.property_id else None
    return render_template("toucan_invoice_detail.html", invoice=invoice, items=items, customer=customer, property=property)



@app.route("/invoice-center/<int:invoice_id>/mark-paid")
@login_required
def mark_invoice_paid(invoice_id):
    invoice = ToucanInvoice.query.get_or_404(invoice_id)
    invoice.status = "Paid"
    db.session.commit()
    flash("Invoice marked as paid.")
    return redirect(url_for("toucan_invoice_detail", invoice_id=invoice.id))





# ===== PROPERTY MAP =====
@app.route("/property-map")
@login_required
def property_map():
    properties = Property.query.order_by(Property.property_name.asc()).all()
    customers = {c.id: c for c in Customer.query.all()}
    return render_template(
        "property_map.html",
        properties=properties,
        customers=customers,
        user=current_user()
    )


@app.route("/properties/geocode")
@login_required
@admin_required
def geocode_properties():
    import time
    import requests

    updated = 0
    skipped = 0
    failed = 0

    props = Property.query.order_by(Property.id.asc()).all()

    for prop in props:
        if getattr(prop, 'latitude', None) and getattr(prop, 'longitude', None):
            skipped += 1
            continue

        if not prop.address:
            failed += 1
            continue

        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": prop.address,
                    "format": "json",
                    "limit": 1
                },
                headers={
                    "User-Agent": "ToucanHVAC/1.0"
                },
                timeout=10
            )

            data = response.json()

            if data:
                setattr(prop, 'latitude', float(data[0]["lat"]))
                setattr(prop, 'longitude', float(data[0]["lon"]))
                updated += 1
                db.session.commit()
            else:
                failed += 1

            time.sleep(1)

        except Exception:
            failed += 1

    failed_addresses = []

    for prop in Property.query.all():
        if prop.latitude and prop.longitude:
            skipped += 1
            continue

        address = ", ".join(filter(None, [
            prop.address,
            getattr(prop, "city", ""),
            getattr(prop, "state", ""),
            getattr(prop, "zip_code", "")
        ])).strip()

        if not address:
            failed += 1
            failed_addresses.append(f"Property ID {prop.id}: Missing address")
            continue

        try:
            lat, lng = google_geocode_address(address)
            prop.latitude = lat
            prop.longitude = lng
            updated += 1

        except Exception as e:
            failed += 1
            failed_addresses.append(f"{address} ({e})")

    db.session.commit()

    msg = f"Geocoding complete. Updated: {updated}. Already had coordinates: {skipped}. Failed: {failed}."

    if failed_addresses:
        msg += " Failed addresses: " + " | ".join(failed_addresses[:10])

    flash(msg)
    return redirect(url_for("property_map"))

@app.route("/reports")
@login_required
@admin_required
def reports_dashboard():
    return render_template("reports.html", user=current_user())




@app.route("/reports/customers/pdf")
@login_required
def report_customers_pdf():
    customers = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    return render_template("report_customers.html", customers=customers, user=current_user())

@app.route("/reports/customers")
@login_required
@admin_required
def report_customers():
    customers = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    return render_template("report_customers.html", customers=customers, user=current_user())


@app.route("/reports/equipment")
@login_required
@admin_required
def report_equipment():
    equipment = Equipment.query.order_by(Equipment.id.desc()).all()
    properties = {p.id: p for p in Property.query.all()}
    customers = {c.id: c for c in Customer.query.all()}
    return render_template("report_equipment.html", equipment=equipment, properties=properties, customers=customers, user=current_user())


@app.route("/reports/invoices")
@login_required
@admin_required
def report_invoices():
    invoices = ToucanInvoice.query.order_by(ToucanInvoice.id.desc()).all()
    customers = {c.id: c for c in Customer.query.all()}
    properties = {p.id: p for p in Property.query.all()}
    return render_template("report_invoices.html", invoices=invoices, customers=customers, properties=properties, user=current_user())


@app.route("/reports/filter-reminders")
@login_required
@admin_required
def report_filter_reminders():
    equipment = Equipment.query.order_by(Equipment.id.desc()).all()
    properties = {p.id: p for p in Property.query.all()}
    customers = {c.id: c for c in Customer.query.all()}
    return render_template("report_filter_reminders.html", equipment=equipment, properties=properties, customers=customers, user=current_user())


@app.route("/reports/filters")
@login_required
@admin_required
def report_filters():
    equipment = Equipment.query.order_by(Equipment.filter_size.asc()).all()
    properties = {p.id: p for p in Property.query.all()}
    customers = {c.id: c for c in Customer.query.all()}
    return render_template("report_filters.html", equipment=equipment, properties=properties, customers=customers, user=current_user())






@app.route("/reports/parts-prices", methods=["GET", "POST"])
@login_required
@admin_required
def report_parts_prices():

    if request.method == "POST":

        part = PartsPrice(
            part_name=request.form.get("part_name"),
            price=float(request.form.get("price") or 0),
            notes=request.form.get("notes")
        )

        db.session.add(part)
        db.session.commit()

        flash("Part added.")

        return redirect(url_for("report_parts_prices"))

    parts = PartsPrice.query.order_by(PartsPrice.part_name.asc()).all()

    return render_template(
        "report_parts_prices.html",
        parts=parts,
        user=current_user()
    )


@app.route("/technicians")
@login_required
@admin_required
def technicians():
    techs = User.query.order_by(User.name.asc()).all()

    return render_template(
        "technicians.html",
        technicians=techs,
        user=current_user()
    )


@app.route("/technicians/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_technician():

    if request.method == "POST":

        user = User(
            name=request.form.get("name"),
            email=request.form.get("email"),
            password=request.form.get("password"),
            role=request.form.get("role") or "technician"
        )

        db.session.add(user)
        db.session.commit()

        flash("Technician added.")

        return redirect(url_for("technicians"))

    return render_template(
        "new_technician.html",
        user=current_user()
    )


@app.route("/technicians/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_technician(user_id):

    technician = User.query.get_or_404(user_id)

    if request.method == "POST":

        technician.name = request.form.get("name")
        technician.email = request.form.get("email")

        if request.form.get("password"):
            technician.password = request.form.get("password")

        technician.role = request.form.get("role")

        db.session.commit()

        flash("Technician updated.")

        return redirect(url_for("technicians"))

    return render_template(
        "edit_technician.html",
        technician=technician,
        user=current_user()
    )



# ===== PDF INVOICE ROUTE - USES REAL INVOICE TEMPLATE =====
@app.route("/equipment/<int:equipment_id>/decode")
def decode_equipment(equipment_id):
    unit = Equipment.query.get_or_404(equipment_id)

    brand = (getattr(unit, "brand", "") or "").strip()
    model = (getattr(unit, "model_number", "") or getattr(unit, "model", "") or "").strip()
    serial = (getattr(unit, "serial_number", "") or "").strip()

    info = {
        "brand": brand,
        "model": model,
        "serial": serial,
        "equipment_type": "Unknown",
        "tonnage": "Unknown",
        "btu": "Unknown",
        "voltage": "Unknown",
        "estimated_age": "Unknown",
        "notes": [],
        "warranty_name": "Google Warranty Search",
        "warranty_url": ""
    }

    brand_upper = brand.upper()

    warranty_links = [
        (["LENNOX"], "Lennox Warranty Lookup", "https://www.lennox.com/residential/owners/assistance/warranty/"),
        (["TRANE", "AMERICAN STANDARD"], "Trane / American Standard Warranty Lookup", "https://www.trane.com/residential/en/resources/warranty-and-registration/"),
        (["GOODMAN", "AMANA", "DAIKIN"], "Goodman / Amana / Daikin Warranty Lookup", "https://www.goodmanmfg.com/support/warranty-lookup"),
        (["NORDYNE", "NORTEK", "INTERTHERM", "MILLER", "FRIGIDAIRE"], "Nortek / Nordyne Warranty Lookup", "https://www.nortekhvacwarranty.com/"),
        (["CARRIER", "BRYANT", "PAYNE"], "Carrier / Bryant / Payne Warranty Lookup", "https://www.carrier.com/residential/en/us/warranty-lookup/"),
        (["RHEEM", "RUUD"], "Rheem / Ruud Warranty Lookup", "https://www.rheem.com/warranty/"),
        (["YORK", "COLEMAN", "LUXAIRE"], "York / Coleman / Luxaire Warranty Lookup", "https://www.york.com/residential-equipment/warranty-and-registration"),
        (["ICP", "TEMPSTAR", "COMFORTMAKER", "HEIL", "ARCOAIRE"], "ICP Warranty Lookup", "https://www.icpusa.com/en/us/warranty/"),
    ]

    for names, label, url in warranty_links:
        if any(name in brand_upper for name in names):
            info["warranty_name"] = label
            info["warranty_url"] = url
            break

    if not info["warranty_url"]:
        info["warranty_url"] = "https://www.google.com/search?q=" + quote_plus(f"{brand} warranty lookup {serial}")

    # Lennox model decoder example: 14HPX-042-230-19
    if "LENNOX" in brand.upper() or model.upper().startswith(("14HPX", "13ACX", "ML14", "ML17", "EL16", "XC", "XP")):
        m = model.upper()

        if "HP" in m or "XP" in m:
            info["equipment_type"] = "Heat Pump Condenser"
        elif "AC" in m or "XC" in m:
            info["equipment_type"] = "Air Conditioner Condenser"

        ton_map = {
            "018": ("1.5 ton", "18,000 BTU"),
            "024": ("2 ton", "24,000 BTU"),
            "030": ("2.5 ton", "30,000 BTU"),
            "036": ("3 ton", "36,000 BTU"),
            "042": ("3.5 ton", "42,000 BTU"),
            "048": ("4 ton", "48,000 BTU"),
            "060": ("5 ton", "60,000 BTU"),
        }

        for code, values in ton_map.items():
            if code in m:
                info["tonnage"], info["btu"] = values
                break

        if "230" in m:
            info["voltage"] = "208/230 volt"

        # Lennox serial example: 1915G27047 = 2015, G = July
        months = {
            "A": "January", "B": "February", "C": "March", "D": "April",
            "E": "May", "F": "June", "G": "July", "H": "August",
            "J": "September", "K": "October", "L": "November", "M": "December"
        }

        s = serial.upper()
        if len(s) >= 5 and s[2:4].isdigit():
            year = "20" + s[2:4]
            month = months.get(s[4], "")
            if month:
                info["estimated_age"] = f"Manufactured around {month} {year}"
            else:
                info["estimated_age"] = f"Manufactured around {year}"

        info["notes"].append("Lennox decoding is an estimate. Always verify with the manufacturer or distributor.")

    return render_template("equipment_decode.html", unit=unit, info=info)




@app.route("/equipment/<int:equipment_id>/warranty", methods=["POST"])
def update_equipment_warranty(equipment_id):
    unit = Equipment.query.get_or_404(equipment_id)

    unit.warranty_status = request.form.get("warranty_status", "")
    unit.warranty_expiration = request.form.get("warranty_expiration", "")
    unit.warranty_last_checked = request.form.get("warranty_last_checked", "")
    unit.warranty_notes = request.form.get("warranty_notes", "")

    db.session.commit()
    return redirect(f"/equipment/{equipment_id}")




@app.route("/reports/pricing")
@login_required
def pricing_report():
    items = PriceItem.query.order_by(PriceItem.category.asc(), PriceItem.part_name.asc()).all()
    return render_template("pricing_report.html", items=items)


@app.route("/reports/pricing/add", methods=["POST"])
@login_required
def add_price_item():

    item = PriceItem(
        part_name=request.form.get("part_name"),
        category=request.form.get("category"),
        price=float(request.form.get("price") or 0),
        notes=request.form.get("notes"),
    )

    db.session.add(item)
    db.session.commit()

    return redirect("/reports/pricing")




@app.route("/price-list")
@app.route("/parts-price-list")
@login_required
def price_list_shortcut():
    return redirect("/reports/pricing")




# ---- Invoice URL aliases / export fallbacks ----
@app.route("/invoice/<int:invoice_id>")
@app.route("/invoices/<int:invoice_id>")
@login_required
def invoice_alias(invoice_id):
    return redirect(f"/invoice-center/{invoice_id}")


@app.route("/invoice/<int:invoice_id>/pdf")
@app.route("/invoices/<int:invoice_id>/pdf")
@login_required
def invoice_pdf_fallback(invoice_id):
    flash("PDF export is disabled for now. Use Print Invoice, then Save as PDF.")
    return redirect(f"/invoice-center/{invoice_id}")







@app.route("/invoice/<int:invoice_id>/jpg")
@app.route("/invoices/<int:invoice_id>/jpg")
@app.route("/invoice-center/<int:invoice_id>/jpg")
@login_required
def invoice_jpg(invoice_id):
    from flask import request, send_file
    from pathlib import Path
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright

    export_dir = Path("static/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / f"invoice_{invoice_id}.jpg"

    invoice_url = request.host_url.rstrip("/") + f"/invoice-center/{invoice_id}"
    parsed = urlparse(request.host_url)
    host = parsed.hostname or "127.0.0.1"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1000, "height": 1400}, device_scale_factor=2)

        for name, value in request.cookies.items():
            context.add_cookies([{
                "name": name,
                "value": value,
                "domain": host,
                "path": "/"
            }])

        page = context.new_page()
        page.goto(invoice_url, wait_until="networkidle")

        page.add_style_tag(content="""
            header, nav, footer,
            .top-nav, .navbar, .nav, .site-header,
            .action-bar, .action-btn, .toolbar, .button-row,
            button, form, .flash, .messages, .alert,
            .no-print, .hide-print {
                display: none !important;
                visibility: hidden !important;
            }

            body {
                background: white !important;
                margin: 0 !important;
                padding: 0 !important;
            }

            main, .container, .content, .page, .card {
                box-shadow: none !important;
            }
        """)

        handle = page.evaluate_handle("""
        () => {
            const selectors = [
                '.paper-invoice',
                '.invoice-paper',
                '.invoice-page',
                '.toucan-invoice',
                '.print-invoice',
                '.invoice-sheet',
                '#invoice',
                '#invoice-paper'
            ];

            for (const s of selectors) {
                const el = document.querySelector(s);
                if (el) return el;
            }

            const all = Array.from(document.querySelectorAll('div, main, section, article'));
            const candidates = all
                .filter(el => {
                    const txt = (el.innerText || '').toLowerCase();
                    const r = el.getBoundingClientRect();
                    return txt.includes('invoice') && r.width > 400 && r.height > 400;
                })
                .sort((a, b) => {
                    const ar = a.getBoundingClientRect();
                    const br = b.getBoundingClientRect();
                    return (br.width * br.height) - (ar.width * ar.height);
                });

            return candidates[0] || document.body;
        }
        """)

        element = handle.as_element()
        element.screenshot(path=str(output_path), type="jpeg", quality=95)

        browser.close()

    return send_file(output_path, mimetype="image/jpeg", as_attachment=True, download_name=f"invoice_{invoice_id}.jpg")


class MonitoringAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("monitoring_device.id"), nullable=False)
    reading_id = db.Column(db.Integer, db.ForeignKey("sensor_reading.id"), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    alert_type = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.String(50), nullable=False, default="warning")
    message = db.Column(db.Text, nullable=False)
    resolved = db.Column(db.Boolean, default=False)

    send_sms = db.Column(db.Boolean, default=False)
    sms_phone_number = db.Column(db.String(50), nullable=True)

    send_email = db.Column(db.Boolean, default=False)
    email_address = db.Column(db.String(150), nullable=True)

    notification_sent = db.Column(db.Boolean, default=False)
    notification_sent_at = db.Column(db.DateTime, nullable=True)


@app.route("/api/monitoring/upload", methods=["POST"])
def upload_monitoring_data():
    data = request.get_json(silent=True) or {}

    device_uid = data.get("device_uid")
    api_key = data.get("api_key")

    if not device_uid:
        return {"ok": False, "error": "Missing device_uid"}, 400

    if not api_key:
        return {"ok": False, "error": "Missing api_key"}, 401

    device = MonitoringDevice.query.filter_by(device_uid=device_uid).first()

    if not device:
        return {"ok": False, "error": "Unknown device"}, 404

    if not device.api_key or device.api_key != api_key:
        return {"ok": False, "error": "Invalid api_key"}, 403

    supply_temp = data.get("supply_temp")
    return_temp = data.get("return_temp")

    temp_split = None
    if supply_temp is not None and return_temp is not None:
        temp_split = float(return_temp) - float(supply_temp)

    reading = SensorReading(
        device_id=device.id,
        supply_temp=supply_temp,
        return_temp=return_temp,
        attic_temp=data.get("attic_temp"),
        humidity=data.get("humidity"),
        temp_split=temp_split,
        overflow_alert=bool(data.get("overflow_alert", False)),
        system_running=bool(data.get("system_running", False)),
        raw_json=str(data)
    )

    device.last_seen = datetime.utcnow()

    db.session.add(reading)
    db.session.flush()

    alerts = []

    if reading.overflow_alert:
        alerts.append(MonitoringAlert(
            device_id=device.id,
            reading_id=reading.id,
            alert_type="condensate_overflow",
            severity="danger",
            message="Condensate overflow switch is triggered."
        ))

    if reading.temp_split is not None and reading.system_running:
        if reading.temp_split < 14:
            alerts.append(MonitoringAlert(
                device_id=device.id,
                reading_id=reading.id,
                alert_type="low_temp_split",
                severity="warning",
                message=f"Low cooling temperature split detected: {reading.temp_split:.1f}°F."
            ))

        if reading.temp_split > 24:
            alerts.append(MonitoringAlert(
                device_id=device.id,
                reading_id=reading.id,
                alert_type="high_temp_split",
                severity="warning",
                message=f"High cooling temperature split detected: {reading.temp_split:.1f}°F."
            ))

    if reading.attic_temp is not None and reading.attic_temp > 120:
        alerts.append(MonitoringAlert(
            device_id=device.id,
            reading_id=reading.id,
            alert_type="high_attic_temp",
            severity="warning",
            message=f"High attic temperature detected: {reading.attic_temp:.1f}°F."
        ))

    notification_setting = MonitoringNotificationSetting.query.first()

    for alert in alerts:
        if notification_setting:
            alert.send_sms = bool(notification_setting.sms_enabled)
            alert.sms_phone_number = notification_setting.sms_phone_number

            alert.send_email = bool(notification_setting.email_enabled)
            alert.email_address = notification_setting.email_address

        db.session.add(alert)

    db.session.commit()

    return {
        "ok": True,
        "message": "Reading saved",
        "device_id": device.id,
        "reading_id": reading.id,
        "temp_split": temp_split,
        "alerts_created": len(alerts)
    }


@app.route("/monitoring")
def monitoring_dashboard():
    devices = MonitoringDevice.query.order_by(MonitoringDevice.id.desc()).all()

    latest_readings = {}
    for device in devices:
        latest = SensorReading.query.filter_by(device_id=device.id).order_by(SensorReading.timestamp.desc()).first()
        latest_readings[device.id] = latest

    return render_template(
        "monitoring.html",
        devices=devices,
        latest_readings=latest_readings
    )




@app.route("/monitoring/device/<int:device_id>")
def monitoring_device_detail(device_id):
    device = MonitoringDevice.query.get_or_404(device_id)

    readings = SensorReading.query.filter_by(device_id=device.id).order_by(SensorReading.timestamp.asc()).limit(100).all()

    labels = [r.timestamp.strftime("%m/%d %H:%M") for r in readings]
    supply_data = [r.supply_temp for r in readings]
    return_data = [r.return_temp for r in readings]
    split_data = [r.temp_split for r in readings]
    humidity_data = [r.humidity for r in readings]
    attic_data = [r.attic_temp for r in readings]

    latest = readings[-1] if readings else None

    return render_template(
        "monitoring_device_detail.html",
        device=device,
        readings=readings,
        latest=latest,
        labels=labels,
        supply_data=supply_data,
        return_data=return_data,
        split_data=split_data,
        humidity_data=humidity_data,
        attic_data=attic_data
    )





class MonitoringNotificationSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    sms_enabled = db.Column(db.Boolean, default=False)
    sms_phone_number = db.Column(db.String(50), nullable=True)

    email_enabled = db.Column(db.Boolean, default=False)
    email_address = db.Column(db.String(150), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True)


@app.route("/monitoring/alerts")
def monitoring_alerts():
    alerts = MonitoringAlert.query.order_by(MonitoringAlert.timestamp.desc()).limit(100).all()
    return render_template("monitoring_alerts.html", alerts=alerts)




@app.route("/monitoring/notification-settings", methods=["GET", "POST"])
def monitoring_notification_settings():
    setting = MonitoringNotificationSetting.query.first()

    if not setting:
        setting = MonitoringNotificationSetting()
        db.session.add(setting)
        db.session.commit()

    if request.method == "POST":
        setting.sms_enabled = True if request.form.get("sms_enabled") == "on" else False
        setting.sms_phone_number = request.form.get("sms_phone_number", "").strip()

        setting.email_enabled = True if request.form.get("email_enabled") == "on" else False
        setting.email_address = request.form.get("email_address", "").strip()

        setting.updated_at = datetime.utcnow()

        db.session.commit()
        flash("Monitoring notification settings saved.")
        return redirect("/monitoring/notification-settings")

    return render_template("monitoring_notification_settings.html", setting=setting)




@app.route("/monitoring/devices")
def monitoring_devices():
    devices = MonitoringDevice.query.order_by(MonitoringDevice.id.desc()).all()
    return render_template("monitoring_devices.html", devices=devices)




@app.route("/monitoring/pending-notifications")
def monitoring_pending_notifications():
    alerts = MonitoringAlert.query.filter(
        MonitoringAlert.notification_sent == False,
        ((MonitoringAlert.send_sms == True) | (MonitoringAlert.send_email == True))
    ).order_by(MonitoringAlert.timestamp.desc()).limit(100).all()

    return render_template("monitoring_pending_notifications.html", alerts=alerts)







# =========================
# TOUCAN HVAC INVENTORY V2
# =========================

def inventory_db_path():
    candidates = [
        Path("instance/hvac.db"),
        Path("instance/app.db"),
        Path("hvac.db"),
        Path("app.db"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("instance/hvac.db")

def inventory_conn():
    db = inventory_db_path()
    db.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn

def init_inventory_v2():
    conn = inventory_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            part_name TEXT NOT NULL,
            part_number TEXT,
            description TEXT,
            unit_cost REAL DEFAULT 0,
            sell_price REAL DEFAULT 0,
            min_quantity INTEGER DEFAULT 0,
            supplier TEXT,
            notes TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_name TEXT NOT NULL,
            location_type TEXT DEFAULT 'Truck'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            location_id INTEGER,
            transaction_type TEXT,
            quantity INTEGER,
            job_id TEXT,
            invoice_id TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add missing columns if upgrading old table
    existing_cols = [r["name"] for r in cur.execute("PRAGMA table_info(inventory_items)").fetchall()]
    for col, ddl in {
        "part_number": "ALTER TABLE inventory_items ADD COLUMN part_number TEXT",
        "sell_price": "ALTER TABLE inventory_items ADD COLUMN sell_price REAL DEFAULT 0",
    }.items():
        if col not in existing_cols:
            cur.execute(ddl)

    # Default locations
    count = cur.execute("SELECT COUNT(*) AS c FROM inventory_locations").fetchone()["c"]
    if count == 0:
        cur.execute("INSERT INTO inventory_locations (location_name, location_type) VALUES ('Shop', 'Shop')")
        cur.execute("INSERT INTO inventory_locations (location_name, location_type) VALUES ('Stephen Truck', 'Truck')")

    conn.commit()
    conn.close()

@app.route("/inventory")
def inventory():
    init_inventory_v2()
    conn = inventory_conn()
    cur = conn.cursor()

    items = cur.execute("""
        SELECT i.*,
        COALESCE(SUM(s.quantity),0) AS total_qty,
        CASE WHEN COALESCE(SUM(s.quantity),0) <= i.min_quantity THEN 1 ELSE 0 END AS low_stock
        FROM inventory_items i
        LEFT JOIN inventory_stock s ON s.item_id = i.id
        GROUP BY i.id
        ORDER BY i.category, i.part_name
    """).fetchall()

    locations = cur.execute("SELECT * FROM inventory_locations ORDER BY location_name").fetchall()
    conn.close()
    return render_template("inventory.html", items=items, locations=locations)

@app.route("/inventory/add", methods=["POST"])
def inventory_add():
    init_inventory_v2()
    conn = inventory_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO inventory_items
        (category, part_name, part_number, description, unit_cost, sell_price, min_quantity, supplier, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form.get("category",""),
        request.form.get("part_name",""),
        request.form.get("part_number",""),
        request.form.get("description",""),
        float(request.form.get("unit_cost") or 0),
        float(request.form.get("sell_price") or 0),
        int(request.form.get("min_quantity") or 0),
        request.form.get("supplier",""),
        request.form.get("notes",""),
    ))
    item_id = cur.lastrowid

    for loc in cur.execute("SELECT id FROM inventory_locations").fetchall():
        qty = int(request.form.get(f"qty_{loc['id']}") or 0)
        cur.execute("INSERT INTO inventory_stock (item_id, location_id, quantity) VALUES (?, ?, ?)",
                    (item_id, loc["id"], qty))

    conn.commit()
    conn.close()
    return redirect("/inventory")

@app.route("/inventory/locations", methods=["POST"])
def inventory_add_location():
    init_inventory_v2()
    conn = inventory_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO inventory_locations (location_name, location_type) VALUES (?, ?)",
                (request.form.get("location_name",""), request.form.get("location_type","Truck")))
    conn.commit()
    conn.close()
    return redirect("/inventory")

@app.route("/inventory/<int:item_id>/edit", methods=["GET", "POST"])
def inventory_edit(item_id):
    init_inventory_v2()
    conn = inventory_conn()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute("""
            UPDATE inventory_items
            SET category=?, part_name=?, part_number=?, description=?, unit_cost=?, sell_price=?, min_quantity=?, supplier=?, notes=?
            WHERE id=?
        """, (
            request.form.get("category",""),
            request.form.get("part_name",""),
            request.form.get("part_number",""),
            request.form.get("description",""),
            float(request.form.get("unit_cost") or 0),
            float(request.form.get("sell_price") or 0),
            int(request.form.get("min_quantity") or 0),
            request.form.get("supplier",""),
            request.form.get("notes",""),
            item_id
        ))

        for loc in cur.execute("SELECT id FROM inventory_locations").fetchall():
            qty = int(request.form.get(f"qty_{loc['id']}") or 0)
            existing = cur.execute("SELECT id FROM inventory_stock WHERE item_id=? AND location_id=?",
                                   (item_id, loc["id"])).fetchone()
            if existing:
                cur.execute("UPDATE inventory_stock SET quantity=? WHERE id=?", (qty, existing["id"]))
            else:
                cur.execute("INSERT INTO inventory_stock (item_id, location_id, quantity) VALUES (?, ?, ?)",
                            (item_id, loc["id"], qty))

        conn.commit()
        conn.close()
        return redirect("/inventory")

    item = cur.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    locations = cur.execute("""
        SELECT l.*, COALESCE(s.quantity,0) AS quantity
        FROM inventory_locations l
        LEFT JOIN inventory_stock s ON s.location_id = l.id AND s.item_id = ?
        ORDER BY l.location_name
    """, (item_id,)).fetchall()

    conn.close()
    return render_template("inventory_edit.html", item=item, locations=locations)

@app.route("/inventory/<int:item_id>/use", methods=["POST"])
def inventory_use(item_id):
    init_inventory_v2()
    conn = inventory_conn()
    cur = conn.cursor()

    location_id = int(request.form.get("location_id"))
    qty = int(request.form.get("quantity") or 1)
    job_id = request.form.get("job_id","")
    invoice_id = request.form.get("invoice_id","")
    note = request.form.get("note","")

    existing = cur.execute("SELECT id, quantity FROM inventory_stock WHERE item_id=? AND location_id=?",
                           (item_id, location_id)).fetchone()

    if existing:
        new_qty = max(0, existing["quantity"] - qty)
        cur.execute("UPDATE inventory_stock SET quantity=? WHERE id=?", (new_qty, existing["id"]))

    cur.execute("""
        INSERT INTO inventory_transactions
        (item_id, location_id, transaction_type, quantity, job_id, invoice_id, note)
        VALUES (?, ?, 'USED', ?, ?, ?, ?)
    """, (item_id, location_id, qty, job_id, invoice_id, note))

    conn.commit()
    conn.close()
    return redirect("/inventory")

@app.route("/inventory/<int:item_id>/delete", methods=["POST"])
def inventory_delete(item_id):
    init_inventory_v2()
    conn = inventory_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM inventory_transactions WHERE item_id=?", (item_id,))
    cur.execute("DELETE FROM inventory_stock WHERE item_id=?", (item_id,))
    cur.execute("DELETE FROM inventory_items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect("/inventory")

@app.route("/inventory/report/order-needed")
def inventory_order_needed():
    init_inventory_v2()
    conn = inventory_conn()
    cur = conn.cursor()
    items = cur.execute("""
        SELECT i.*, COALESCE(SUM(s.quantity),0) AS total_qty
        FROM inventory_items i
        LEFT JOIN inventory_stock s ON s.item_id = i.id
        GROUP BY i.id
        HAVING total_qty <= i.min_quantity
        ORDER BY i.category, i.part_name
    """).fetchall()
    conn.close()
    return render_template("inventory_order_needed.html", items=items)






# =========================
# TOUCAN NOTIFICATIONS
# =========================

def send_toucan_notification(subject, body):
    smtp_server = os.environ.get("TOUCAN_SMTP_SERVER") or os.environ.get("SMTP_SERVER", "")
    smtp_port = int(os.environ.get("TOUCAN_SMTP_PORT") or os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("TOUCAN_SMTP_USER") or os.environ.get("SMTP_USERNAME", "")
    smtp_password = os.environ.get("TOUCAN_SMTP_PASSWORD") or os.environ.get("SMTP_PASSWORD", "")
    notify_email = os.environ.get("TOUCAN_NOTIFY_EMAIL", "")
    notify_sms = os.environ.get("TOUCAN_NOTIFY_SMS", "")

    if not smtp_server or not smtp_user or not smtp_password:
        print("Toucan notification skipped: SMTP settings missing.")
        return

    recipients = []
    if notify_email:
        recipients.append(notify_email)
    if notify_sms:
        recipients.append(notify_sms)

    if not recipients:
        print("Toucan notification skipped: no recipients.")
        return

    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print("Toucan notification sent.")
    except Exception as e:
        print("Toucan notification failed:", e)


# =========================
# TOUCAN HVAC PUBLIC WEBSITE
# =========================

def public_db_path():
    candidates = [
        Path("instance/hvac.db"),
        Path("instance/app.db"),
        Path("hvac.db"),
        Path("app.db"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("instance/hvac.db")

def init_public_tables():
    db = public_db_path()
    db.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public_service_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            problem TEXT,
            preferred_time TEXT,
            status TEXT DEFAULT 'New',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public_filter_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            filter_size TEXT,
            quantity INTEGER DEFAULT 1,
            frequency TEXT,
            notes TEXT,
            status TEXT DEFAULT 'New',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

@app.route("/public")
def public_home():
    return render_template("public_home.html")

@app.route("/request-service", methods=["GET", "POST"])
def public_request_service():
    init_public_tables()

    if request.method == "POST":
        conn = sqlite3.connect(public_db_path())
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO public_service_requests
            (name, phone, email, address, problem, preferred_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("name", ""),
            request.form.get("phone", ""),
            request.form.get("email", ""),
            request.form.get("address", ""),
            request.form.get("problem", ""),
            request.form.get("preferred_time", "")
        ))
        conn.commit()
        conn.close()

        send_toucan_notification(
            "New Toucan HVAC Service Request",
            f"""New service request from Toucan HVAC website.

Name: {request.form.get('name', '')}
Phone: {request.form.get('phone', '')}
Email: {request.form.get('email', '')}
Address: {request.form.get('address', '')}
Preferred Time: {request.form.get('preferred_time', '')}

Problem:
{request.form.get('problem', '')}
"""
        )

        return render_template("public_thank_you.html", message="Your service request has been sent to Toucan HVAC.")

    return render_template("public_request_service.html")

@app.route("/order-filters", methods=["GET", "POST"])
def public_order_filters():
    init_public_tables()

    if request.method == "POST":
        conn = sqlite3.connect(public_db_path())
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO public_filter_orders
            (name, phone, email, address, filter_size, quantity, frequency, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("name", ""),
            request.form.get("phone", ""),
            request.form.get("email", ""),
            request.form.get("address", ""),
            request.form.get("filter_size", ""),
            int(request.form.get("quantity") or 1),
            request.form.get("frequency", ""),
            request.form.get("notes", "")
        ))
        conn.commit()
        conn.close()

        send_toucan_notification(
            "New Toucan HVAC Filter Order",
            f"""New filter order from Toucan HVAC website.

Name: {request.form.get('name', '')}
Phone: {request.form.get('phone', '')}
Email: {request.form.get('email', '')}
Address: {request.form.get('address', '')}

Filter Size: {request.form.get('filter_size', '')}
Quantity: {request.form.get('quantity', '')}
Frequency: {request.form.get('frequency', '')}

Notes:
{request.form.get('notes', '')}
"""
        )

        return render_template("public_thank_you.html", message="Your filter order request has been sent to Toucan HVAC.")

    return render_template("public_order_filters.html")

@app.route("/service-requests")
def service_requests():
    init_public_tables()
    conn = sqlite3.connect(public_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    requests_list = cur.execute("""
        SELECT * FROM public_service_requests
        ORDER BY created_at DESC
    """).fetchall()

    filter_orders = cur.execute("""
        SELECT * FROM public_filter_orders
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()
    return render_template("service_requests.html", requests_list=requests_list, filter_orders=filter_orders)





# =========================
# TEMP EMERGENCY ADMIN CREATE
# REMOVE AFTER USE
# =========================
@app.route("/setup-admin-now")
def setup_admin_now():
    secret = request.args.get("secret", "")
    if secret != os.environ.get("SETUP_ADMIN_SECRET", ""):
        return "Unauthorized", 403

    email = os.environ.get("SETUP_ADMIN_EMAIL", "admin@toucanhvac.local")
    password = os.environ.get("SETUP_ADMIN_PASSWORD", "ChangeMeNow123!")
    name = os.environ.get("SETUP_ADMIN_NAME", "Stephen Oldham")

    existing = User.query.filter_by(email=email).first()

    if existing:
        existing.name = name
        existing.role = "admin"
        existing.set_password(password)
    else:
        user = User(name=name, email=email, role="admin")
        user.set_password(password)
        db.session.add(user)

    db.session.commit()
    return "Admin user created or reset. You can log in now."




# =========================
# TEMP EMERGENCY DIRECT LOGIN
# REMOVE AFTER USE
# =========================
@app.route("/emergency-login-now")
def emergency_login_now():
    secret = request.args.get("secret", "")
    if secret != os.environ.get("SETUP_ADMIN_SECRET", ""):
        return "Unauthorized", 403

    email = os.environ.get("SETUP_ADMIN_EMAIL", "admin@toucanhvac.local")
    password = os.environ.get("SETUP_ADMIN_PASSWORD", "ChangeMeNow123!")
    name = os.environ.get("SETUP_ADMIN_NAME", "Stephen Oldham")

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(name=name, email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
    else:
        user.name = name
        user.role = "admin"
        user.set_password(password)
        db.session.commit()

    session["user_id"] = user.id
    session["email"] = user.email
    session["role"] = "admin"

    try:
        login_user(user)
    except Exception:
        pass

    return redirect("/dashboard")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)