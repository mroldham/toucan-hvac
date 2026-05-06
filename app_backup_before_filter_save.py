import os
from datetime import datetime
from functools import wraps

from flask import make_response, Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "toucan-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///hvac.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

db = SQLAlchemy(app)
migrate = Migrate(app, db)


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
    phone = db.Column(db.String(50))
    address = db.Column(db.String(255))
    active = db.Column(db.Integer, default=1)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    archived = db.Column(db.Integer, default=0)
    mailing_address = db.Column(db.String(255))

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
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)


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
    last_filter_change = db.Column(db.String(20))
    filter_interval_days = db.Column(db.Integer, default=90)
    filter_brand = db.Column(db.String(120))
    filter_quantity = db.Column(db.String(20))
    filter_notes = db.Column(db.Text)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

class ServiceJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))

    description = db.Column(db.Text)
    scheduled_date = db.Column(db.String(50))
    status = db.Column(db.String(50), default="Scheduled")

    technician = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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



@app.route("/customers", methods=["GET", "POST"])
@login_required
@admin_required
def customers():

    db.create_all()

    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        email = (request.form.get("email") or "").strip().lower()

        existing = None
        if email:
            existing = Customer.query.filter_by(email=email).first()
        if not existing and phone:
            existing = Customer.query.filter_by(phone=phone).first()

        if existing:
            flash("Customer already exists. Opening existing customer.")
            return redirect(url_for("customer_detail", customer_id=existing.id))

        customer = Customer(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            mailing_address=request.form.get("mailing_address")
        )
        db.session.add(customer)
        db.session.commit()
        flash("Customer added.")
        return redirect(url_for("customers"))

    customer_list = Customer.query.filter_by(archived=0).order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()

    photo_counts = {}
    try:
        photo_counts = {
            row.customer_id: row.count
            for row in db.session.query(CustomerPhoto.customer_id, db.func.count(CustomerPhoto.id).label("count"))
            .group_by(CustomerPhoto.customer_id).all()
        }
    except Exception:
        photo_counts = {}

    return render_template("customers.html", customer_list=customer_list, photo_counts=photo_counts)


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

@app.route('/service-jobs')
def service_jobs():
    jobs = ServiceJob.query.all()
    customers = {c.id: c for c in Customer.query.all()}
    properties = {p.id: p for p in Property.query.all()}
    return render_template("service_jobs.html", jobs=jobs, customers=customers, properties=properties)




@app.route("/customers/<int:customer_id>")
@login_required
@admin_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    properties = Property.query.filter_by(customer_id=customer.id).order_by(Property.property_name.asc()).all()

    equipment_by_property = {}
    for prop in properties:
        equipment_by_property[prop.id] = Equipment.query.filter_by(property_id=prop.id).all()

    jobs = ServiceJob.query.filter_by(customer_id=customer.id).order_by(ServiceJob.scheduled_date.desc()).all()
    invoices = ToucanInvoice.query.filter_by(customer_id=customer.id).order_by(ToucanInvoice.id.desc()).all()

    return render_template(
        "customer_detail.html",
        customer=customer,
        properties=properties,
        equipment_by_property=equipment_by_property,
        jobs=jobs,
        invoices=invoices
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
@admin_required
@login_required
def properties(
):
    props = Property.query.order_by(Property.id.desc()).all()
    return render_template("properties.html", properties=props)


@app.route("/properties/<int:property_id>")
@login_required
def property_detail(property_id):
    prop = Property.query.get_or_404(property_id)
    customer = Customer.query.get_or_404(prop.customer_id)
    equipment_list = Equipment.query.filter_by(property_id=prop.id).order_by(Equipment.id.desc()).all()
    photos = PropertyPhoto.query.filter_by(property_id=prop.id).order_by(PropertyPhoto.id.desc()).all()
    return render_template(
        "property_detail.html",
        user=current_user(),
        property=prop,
        customer=customer,
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
@admin_required
@login_required
def equipment(
):
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
@app.route("/customers/<int:customer_id>/edit", methods=["GET","POST"])
@login_required
def edit_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        customer.first_name = request.form.get("first_name")
        customer.last_name = request.form.get("last_name")
        customer.phone = request.form.get("phone")
        customer.email = request.form.get("email")
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
            notes=request.form.get("notes"),


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

        equipment.last_filter_change = request.form.get("last_filter_change")
        equipment.filter_interval_days = int(request.form.get("filter_interval_days") or 90)
        equipment.filter_notes = request.form.get("filter_notes")


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
            technician=request.form.get("technician")
        )
        db.session.add(job)
        db.session.commit()
        flash("Service job added.")
        return redirect(url_for("service_jobs"))

    customers = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    properties = Property.query.order_by(Property.property_name.asc()).all()
    technicians = User.query.filter_by(role="tech").order_by(User.name.asc()).all()

    return render_template(
        "service_job_form.html",
        customers=customers,
        properties=properties,
        technicians=technicians
    )



@app.route("/calendar")
@admin_required
@admin_required
@login_required
def calendar_view():
    jobs = ServiceJob.query.all()
    return render_template("calendar.html", jobs=jobs)


@app.route("/service-jobs/<int:job_id>")
@login_required
def service_job_detail(job_id):
    job = ServiceJob.query.get_or_404(job_id)

    user = current_user()
    if user.role == "tech" and job.technician != user.name:
        flash("Access denied.")
        return redirect(url_for("my_jobs"))

    customer = Customer.query.get(job.customer_id) if job.customer_id else None
    property = Property.query.get(job.property_id) if job.property_id else None
    photos = ServiceJobPhoto.query.filter_by(job_id=job.id).order_by(ServiceJobPhoto.id.desc()).all()
    return render_template("service_job_detail.html", job=job, customer=customer, property=property, photos=photos)


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




@app.route("/my-jobs")
@login_required
def my_jobs():
    user = current_user()

    if user.role == "admin":
        jobs = ServiceJob.query.order_by(ServiceJob.scheduled_date.asc()).all()
    else:
        jobs = ServiceJob.query.filter_by(technician=user.name).order_by(ServiceJob.scheduled_date.asc()).all()

    customers = {c.id: c for c in Customer.query.all()}
    properties = {p.id: p for p in Property.query.all()}

    return render_template("my_jobs.html", jobs=jobs, customers=customers, properties=properties, user=user)



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


class ToucanInvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("toucan_invoice.id"))
    description = db.Column(db.String(255))
    quantity = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    line_total = db.Column(db.Float, default=0)



@app.route("/invoice-center")
@admin_required
@admin_required
@login_required
def invoice_center(
):
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
            invoice_number=request.form.get("invoice_number"),
            invoice_date=request.form.get("invoice_date"),
            status=request.form.get("status") or "Draft",
            notes=request.form.get("notes"),


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

    customers = Customer.query.order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    properties = Property.query.order_by(Property.property_name.asc()).all()
    return render_template("new_toucan_invoice.html", customers=customers, properties=properties, job=job, customer=customer, property=property)


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


@app.route("/reports")
@admin_required
@admin_required
@login_required
def reports_dashboard(
):
    db.create_all()

    invoices = ToucanInvoice.query.all()
    jobs = ServiceJob.query.all()

    total_invoices = len(invoices)
    paid_invoices = [i for i in invoices if i.status == "Paid"]
    open_invoices = [i for i in invoices if i.status != "Paid"]
    past_due_invoices = [i for i in invoices if i.status == "Past Due"]

    total_revenue = sum(i.total or 0 for i in paid_invoices)
    open_invoice_total = sum(i.total or 0 for i in open_invoices)

    upcoming_jobs = [j for j in jobs if j.status in ["Scheduled", "In Progress"]]
    completed_jobs = [j for j in jobs if j.status == "Completed"]
    pending_quotes = [j for j in jobs if j.status == "Pending Quote"]

    return render_template(
        "reports.html",
        total_invoices=total_invoices,
        paid_count=len(paid_invoices),
        open_count=len(open_invoices),
        past_due_count=len(past_due_invoices),
        total_revenue=total_revenue,
        open_invoice_total=open_invoice_total,
        upcoming_jobs=upcoming_jobs,
        completed_jobs=completed_jobs,
        pending_quotes=pending_quotes
    )


@app.context_processor
def inject_user():
    return dict(current_user=current_user)



@app.route("/customers/<int:customer_id>/archive")
@login_required
@admin_required
def archive_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.archived = 1
    db.session.commit()
    flash("Customer archived.")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/restore")
@login_required
@admin_required
def restore_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.archived = 0
    db.session.commit()
    flash("Customer restored.")
    return redirect(url_for("archived_customers"))


@app.route("/customers/archived")
@login_required
@admin_required
def archived_customers():
    customer_list = Customer.query.filter_by(archived=1).order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    return render_template("archived_customers.html", customer_list=customer_list)


@app.route("/reports/customers")
@login_required
@admin_required
def report_customers():
    customers = Customer.query.filter_by(archived=0).order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    return render_template("report_customers.html", customers=customers)


@app.route("/reports/filters")
@login_required
@admin_required
def report_filters():
    equipment = Equipment.query.all()
    return render_template("report_filters.html", equipment=equipment)


@app.route("/reports/filter-due")
@login_required
@admin_required
def report_filter_due():
    equipment = Equipment.query.all()
    return render_template("report_filter_due.html", equipment=equipment)


@app.route("/reports/equipment")
@login_required
@admin_required
def report_equipment():
    equipment = Equipment.query.all()
    return render_template("report_equipment.html", equipment=equipment)


@app.route("/reports/invoices")
@login_required
@admin_required
def report_invoices():
    invoices = ToucanInvoice.query.order_by(ToucanInvoice.id.desc()).all()
    customers = {c.id: c for c in Customer.query.all()}
    return render_template("report_invoices.html", invoices=invoices, customers=customers)



@app.route("/technicians/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_technician():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        address = (request.form.get("address") or "").strip()
        password = request.form.get("password") or "tech123"

        if not name or not email:
            flash("Name and email are required.")
            return redirect(url_for("new_technician"))

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("A user with that email already exists.")
            return redirect(url_for("technicians"))

        tech = User(name=name, email=email, role="tech")
        tech.phone = phone
        tech.address = address
        tech.active = 1

        if hasattr(tech, "set_password"):
            tech.set_password(password)
        elif hasattr(tech, "password_hash"):
            tech.password_hash = generate_password_hash(password)
        else:
            tech.password = password

        db.session.add(tech)
        db.session.commit()

        flash("Technician login created.")
        return redirect(url_for("technicians"))

    return render_template("new_technician.html")



@app.route("/technicians")
@admin_required
@login_required
@admin_required
def technicians(
):
    techs = User.query.order_by(User.name.asc()).all()
    return render_template("technicians.html", techs=techs)



@app.route("/technicians/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_technician(user_id):
    tech = User.query.get_or_404(user_id)

    if request.method == "POST":
        tech.name = request.form.get("name")
        tech.email = request.form.get("email")
        tech.phone = request.form.get("phone")
        tech.address = request.form.get("address")
        tech.role = request.form.get("role")

        password = request.form.get("password")
        if password:
            tech.set_password(password)

        db.session.commit()
        flash("Technician updated.")
        return redirect(url_for("technicians"))

    return render_template("edit_technician.html", tech=tech)



@app.route("/service-jobs/<int:job_id>/status/<status>")
@login_required
def update_job_status_fast(job_id, status):
    job = ServiceJob.query.get_or_404(job_id)

    allowed = ["Scheduled", "In Progress", "Completed", "Needs Parts", "Pending Quote", "Cancelled"]
    if status not in allowed:
        flash("Invalid status.")
        return redirect(url_for("service_job_detail", job_id=job.id))

    user = current_user()

    # Techs may only update their own assigned jobs
    if user.role == "tech" and job.technician != user.name:
        flash("Access denied.")
        return redirect(url_for("my_jobs"))

    job.status = status
    db.session.commit()
    flash("Job status updated.")
    return redirect(url_for("service_job_detail", job_id=job.id))



class ServiceJobPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("service_job.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255))


@app.route("/invoice-center/<int:invoice_id>/pdf")
@login_required
def invoice_pdf_view(invoice_id):
    invoice = ToucanInvoice.query.get_or_404(invoice_id)
    items = ToucanInvoiceItem.query.filter_by(invoice_id=invoice.id).all()
    customer = Customer.query.get(invoice.customer_id) if invoice.customer_id else None
    property = Property.query.get(invoice.property_id) if invoice.property_id else None

    html = render_template(
        "toucan_invoice_detail.html",
        invoice=invoice,
        items=items,
        customer=customer,
        property=property
    )
    return html


@app.route("/reports/customers/pdf")
@login_required
@admin_required
def report_customers_pdf():
    customers = Customer.query.filter_by(archived=0).order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    return render_template("report_customers.html", customers=customers)


@app.route("/reports/filters/pdf")
@login_required
@admin_required
def report_filters_pdf():
    equipment = Equipment.query.all()
    return render_template("report_filters.html", equipment=equipment)


@app.route("/reports/equipment/pdf")
@login_required
@admin_required
def report_equipment_pdf():
    equipment = Equipment.query.all()
    return render_template("report_equipment.html", equipment=equipment)


@app.route("/reports/invoices/pdf")
@login_required
@admin_required
def report_invoices_pdf():
    invoices = ToucanInvoice.query.order_by(ToucanInvoice.id.desc()).all()
    customers = {c.id: c for c in Customer.query.all()}
    return render_template("report_invoices.html", invoices=invoices, customers=customers)



@app.route("/customers/<int:customer_id>/add-property", methods=["GET", "POST"])
@login_required
@admin_required
def add_property_for_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        prop = Property(
            customer_id=customer.id,
            property_name=request.form.get("property_name"),
            address=request.form.get("address")
        )
        db.session.add(prop)
        db.session.commit()
        flash("Property added.")
        return redirect(url_for("customer_detail", customer_id=customer.id))

    return render_template("add_property_for_customer.html", customer=customer)






@app.route("/service-jobs/<int:job_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_service_job(job_id):
    job = ServiceJob.query.get_or_404(job_id)

    if request.method == "POST":
        job.customer_id = request.form.get("customer_id") or None
        job.property_id = request.form.get("property_id") or None
        job.description = request.form.get("description")
        job.scheduled_date = request.form.get("scheduled_date")
        job.status = request.form.get("status")
        job.technician = request.form.get("technician")
        if hasattr(job, "work_performed"):
            job.work_performed = request.form.get("work_performed")
        if hasattr(job, "notes"):
            job.notes = request.form.get("notes")

        db.session.commit()
        flash("Job updated.")
        return redirect(url_for("service_job_detail", job_id=job.id))

    customers = Customer.query.filter_by(archived=0).order_by(Customer.last_name.asc(), Customer.first_name.asc()).all()
    properties = Property.query.order_by(Property.property_name.asc()).all()
    technicians = User.query.filter_by(role="tech").order_by(User.name.asc()).all()

    return render_template(
        "edit_service_job.html",
        job=job,
        customers=customers,
        properties=properties,
        technicians=technicians
    )



@app.route("/reports/filter-reminders")
@login_required
@admin_required
def report_filter_reminders():
    from datetime import datetime, timedelta

    equipment = Equipment.query.all()
    rows = []

    for eq in equipment:
        next_due = ""
        due_status = "No date entered"

        if eq.last_filter_change:
            try:
                last = datetime.strptime(eq.last_filter_change, "%Y-%m-%d")
                interval = eq.filter_interval_days or 90
                due = last + timedelta(days=interval)
                next_due = due.strftime("%Y-%m-%d")

                if due.date() <= datetime.today().date():
                    due_status = "DUE NOW"
                else:
                    due_status = "Upcoming"
            except Exception:
                due_status = "Bad date"

        rows.append({
            "eq": eq,
            "next_due": next_due,
            "due_status": due_status
        })

    return render_template("report_filter_reminders.html", rows=rows)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
