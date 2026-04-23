import os
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
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


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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


@app.route("/customers")
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
        photo_counts=photo_counts
    )


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
    photos = CustomerPhoto.query.filter_by(customer_id=customer.id).order_by(CustomerPhoto.id.desc()).all()
    return render_template(
        "customer_detail.html",
        user=current_user(),
        customer=customer,
        properties=properties,
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
    photo_counts = {
        row.property_id: row.count
        for row in db.session.query(
            PropertyPhoto.property_id,
            db.func.count(PropertyPhoto.id).label("count")
        ).group_by(PropertyPhoto.property_id).all()
    }

    for prop in property_list:
        customer = Customer.query.get(prop.customer_id)
        rows.append({
            "property": prop,
            "customer": customer,
            "photo_count": photo_counts.get(prop.id, 0)
        })
    return render_template("properties.html", user=current_user(), rows=rows)


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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
