@app.route("/reset-admin-now")
def reset_admin_now():
    from werkzeug.security import generate_password_hash

    email = "admin@toucanhvac.com"
    password = "admin123"

    user = User.query.filter_by(email=email).first()

    if not user:
        user = User()
        user.email = email
        user.password_hash = generate_password_hash(password)
        if hasattr(User, "role"):
            user.role = "admin"
        db.session.add(user)
        db.session.commit()
        return "Admin created"

    user.password_hash = generate_password_hash(password)
    if hasattr(User, "role"):
        user.role = "admin"
    db.session.commit()
    return "Admin reset"
from datetime import datetime
from functools import wraps
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///toucan_hvac.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "toucan-hvac-dev-key"

db = SQLAlchemy(app)


def money_to_float(value):
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0


def generate_invoice_number():
    today = datetime.now().strftime("%Y%m%d")
    count_today = Invoice.query.filter(Invoice.invoice_date.like(f"{datetime.now().strftime('%Y-%m-%d')}%")).count() + 1
    return f"TCH-{today}-{count_today:03d}"



def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


@app.context_processor
def inject_user():
    user = current_user()
    return {
        "current_user": user,
        "is_admin": bool(user and user.role == "admin"),
        "is_technician": bool(user and user.role == "technician"),
    }


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please log in.")
            return redirect(url_for("login"))
        if user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="technician")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    notes = db.Column(db.Text)

    properties = db.relationship("Property", backref="customer", cascade="all, delete-orphan", lazy=True)
    invoices = db.relationship("Invoice", backref="customer", cascade="all, delete-orphan", lazy=True)
    jobs = db.relationship("Job", backref="customer", cascade="all, delete-orphan", lazy=True)


class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    gate_code = db.Column(db.String(50))
    notes = db.Column(db.Text)

    equipment = db.relationship("Equipment", backref="property", cascade="all, delete-orphan", lazy=True)
    invoices = db.relationship("Invoice", backref="property", cascade="all, delete-orphan", lazy=True)
    jobs = db.relationship("Job", backref="property", cascade="all, delete-orphan", lazy=True)


class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)

    unit_label = db.Column(db.String(100))
    unit_type = db.Column(db.String(100))
    brand = db.Column(db.String(100))
    model = db.Column(db.String(100))
    serial_number = db.Column(db.String(100))
    tonnage = db.Column(db.String(50))
    refrigerant = db.Column(db.String(50))
    filter_size = db.Column(db.String(100))
    install_date = db.Column(db.String(50))
    warranty_expiration = db.Column(db.String(50))
    voltage = db.Column(db.String(50))
    belt_size = db.Column(db.String(50))
    location_on_property = db.Column(db.String(150))
    notes = db.Column(db.Text)

    service_visits = db.relationship("ServiceVisit", backref="equipment", cascade="all, delete-orphan", lazy=True)
    jobs = db.relationship("Job", backref="equipment", lazy=True)


class ServiceVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=False)
    visit_date = db.Column(db.String(50), default=lambda: datetime.now().strftime("%Y-%m-%d"))
    technician_name = db.Column(db.String(120))
    problem_reported = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    work_performed = db.Column(db.Text)
    parts_used = db.Column(db.Text)
    amount_charged = db.Column(db.String(50))
    notes = db.Column(db.Text)


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_date = db.Column(db.String(50), default=lambda: datetime.now().strftime("%Y-%m-%d"))
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=True)

    job_type = db.Column(db.String(50))
    status = db.Column(db.String(50), default="Scheduled")

    problem_reported = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    work_performed = db.Column(db.Text)
    parts_used = db.Column(db.Text)
    amount_charged = db.Column(db.String(50))
    notes = db.Column(db.Text)
    technician_name = db.Column(db.String(120))
    technician_name = db.Column(db.String(120))


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"))
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.String(50))
    description = db.Column(db.Text)
    amount = db.Column(db.String(50))
    status = db.Column(db.String(50), default="Unpaid")
    notes = db.Column(db.Text)


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


@app.route("/")
@login_required
def dashboard():
    user = current_user()

    customers = Customer.query.order_by(Customer.id.desc()).limit(10).all()
    recent_jobs = Job.query.order_by(Job.id.desc()).limit(10).all()

    if user.role != "admin":
        return render_template(
            "dashboard.html",
            recent_jobs=recent_jobs,
            customers=customers,
            technician_view=True
        )

    invoices = Invoice.query.order_by(Invoice.id.desc()).limit(10).all()

    all_invoices = Invoice.query.all()
    unpaid_invoices = [inv for inv in all_invoices if (inv.status or "").lower() == "unpaid"]
    paid_invoices = [inv for inv in all_invoices if (inv.status or "").lower() == "paid"]

    unpaid_total = sum(money_to_float(inv.amount) for inv in unpaid_invoices)

    current_month = datetime.now().strftime("%Y-%m")
    paid_this_month_list = [
        inv for inv in paid_invoices
        if inv.invoice_date and str(inv.invoice_date).startswith(current_month)
    ]
    paid_this_month_total = sum(money_to_float(inv.amount) for inv in paid_this_month_list)
    invoice_count_this_month = len(paid_this_month_list)

    all_jobs = Job.query.all()
    scheduled_jobs = [job for job in all_jobs if (job.status or "") == "Scheduled"]
    open_jobs = [job for job in all_jobs if (job.status or "") == "Open"]
    completed_jobs = [job for job in all_jobs if (job.status or "") == "Completed"]
    billed_jobs = [job for job in all_jobs if (job.status or "") == "Billed"]
    unbilled_jobs = [job for job in all_jobs if (job.status or "") != "Billed"]
    unbilled_job_total = sum(money_to_float(job.amount_charged) for job in unbilled_jobs)

    return render_template(
        "dashboard.html",
        customers=customers,
        invoices=invoices,
        recent_jobs=recent_jobs,
        unpaid_total=unpaid_total,
        paid_this_month_total=paid_this_month_total,
        invoice_count_this_month=invoice_count_this_month,
        unpaid_count=len(unpaid_invoices),
        scheduled_count=len(scheduled_jobs),
        open_count=len(open_jobs),
        completed_count=len(completed_jobs),
        billed_count=len(billed_jobs),
        unbilled_count=len(unbilled_jobs),
        unbilled_job_total=unbilled_job_total,
        technician_view=False
    )


@app.route("/users")
@admin_required
def users():
    all_users = User.query.order_by(User.name.asc()).all()
    return render_template("users.html", users=all_users)


@app.route("/users/add", methods=["POST"])
@admin_required
def add_user():
    email = request.form.get("email", "").strip().lower()

    existing = User.query.filter_by(email=email).first()
    if existing:
        flash("A user with that email already exists.")
        return redirect(url_for("users"))

    user = User(
        name=request.form.get("name"),
        email=email,
        role=request.form.get("role")
    )
    user.set_password(request.form.get("password"))

    db.session.add(user)
    db.session.commit()
    flash("User created.")
    return redirect(url_for("users"))


@app.route("/customers")
@login_required
def customers():
    all_customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template("customers.html", customers=all_customers)


@app.route("/customers/add", methods=["POST"])
@login_required
def add_customer():
    customer = Customer(
        name=request.form.get("name"),
        phone=request.form.get("phone"),
        email=request.form.get("email"),
        notes=request.form.get("notes")
    )
    db.session.add(customer)
    db.session.commit()
    flash("Customer added.")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    return render_template("customer_detail.html", customer=customer)


@app.route("/customers/<int:customer_id>/properties/add", methods=["POST"])
@login_required
def add_property(customer_id):
    property_record = Property(
        customer_id=customer_id,
        address=request.form.get("address"),
        gate_code=request.form.get("gate_code"),
        notes=request.form.get("notes")
    )
    db.session.add(property_record)
    db.session.commit()
    flash("Property added.")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/properties/<int:property_id>")
@login_required
def property_detail(property_id):
    property_record = Property.query.get_or_404(property_id)
    return render_template("property_detail.html", property=property_record)


@app.route("/properties/<int:property_id>/equipment/add", methods=["POST"])
@login_required
def add_equipment(property_id):
    equipment = Equipment(
        property_id=property_id,
        unit_label=request.form.get("unit_label"),
        unit_type=request.form.get("unit_type"),
        brand=request.form.get("brand"),
        model=request.form.get("model"),
        serial_number=request.form.get("serial_number"),
        tonnage=request.form.get("tonnage"),
        refrigerant=request.form.get("refrigerant"),
        filter_size=request.form.get("filter_size"),
        install_date=request.form.get("install_date"),
        warranty_expiration=request.form.get("warranty_expiration"),
        voltage=request.form.get("voltage"),
        belt_size=request.form.get("belt_size"),
        location_on_property=request.form.get("location_on_property"),
        notes=request.form.get("notes")
    )
    db.session.add(equipment)
    db.session.commit()
    flash("Equipment added.")
    return redirect(url_for("property_detail", property_id=property_id))


@app.route("/equipment/<int:equipment_id>")
@login_required
def equipment_detail(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    return render_template("equipment_detail.html", equipment=equipment)


@app.route("/equipment/<int:equipment_id>/service/add", methods=["POST"])
@login_required
def add_service_visit(equipment_id):
    visit = ServiceVisit(
        equipment_id=equipment_id,
        visit_date=request.form.get("visit_date"),
        technician_name=request.form.get("technician_name"),
        problem_reported=request.form.get("problem_reported"),
        diagnosis=request.form.get("diagnosis"),
        work_performed=request.form.get("work_performed"),
        parts_used=request.form.get("parts_used"),
        amount_charged=request.form.get("amount_charged"),
        notes=request.form.get("notes")
    )
    db.session.add(visit)
    db.session.commit()
    flash("Service visit added.")
    return redirect(url_for("equipment_detail", equipment_id=equipment_id))


@app.route("/jobs")
@login_required
def jobs():
    all_jobs = Job.query.order_by(Job.id.desc()).all()
    all_customers = Customer.query.order_by(Customer.name.asc()).all()
    all_properties = Property.query.order_by(Property.address.asc()).all()
    all_equipment = Equipment.query.order_by(Equipment.id.desc()).all()
    return render_template(
        "jobs.html",
        jobs=all_jobs,
        customers=all_customers,
        properties=all_properties,
        equipment_list=all_equipment
    )


@app.route("/jobs/add", methods=["POST"])
@login_required
def add_job():
    equipment_id = request.form.get("equipment_id") or None

    user = current_user()

    job = Job(
        technician_name=user.name if user else None,
        job_date=request.form.get("job_date") or datetime.now().strftime("%Y-%m-%d"),
        customer_id=request.form.get("customer_id"),
        property_id=request.form.get("property_id"),
        equipment_id=equipment_id,
        job_type=request.form.get("job_type"),
        status=request.form.get("status"),
        problem_reported=request.form.get("problem_reported"),
        diagnosis=request.form.get("diagnosis"),
        work_performed=request.form.get("work_performed"),
        parts_used=request.form.get("parts_used"),
        amount_charged=request.form.get("amount_charged"),
        notes=request.form.get("notes")
    )
    db.session.add(job)
    db.session.commit()
    flash("Job added.")
    return redirect(url_for("jobs"))


@app.route("/jobs/<int:job_id>")
@login_required
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    return render_template("job_detail.html", job=job)


@app.route("/jobs/<int:job_id>/update", methods=["POST"])
@login_required
def update_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.job_date = request.form.get("job_date")
    job.job_type = request.form.get("job_type")
    job.status = request.form.get("status")
    job.problem_reported = request.form.get("problem_reported")
    job.diagnosis = request.form.get("diagnosis")
    job.work_performed = request.form.get("work_performed")
    job.parts_used = request.form.get("parts_used")
    job.amount_charged = request.form.get("amount_charged")
    job.notes = request.form.get("notes")
    user = current_user()
    if user:
        job.technician_name = user.name
    db.session.commit()
    flash("Job updated.")
    return redirect(url_for("job_detail", job_id=job.id))


@app.route("/invoices")
@admin_required
def invoices():
    all_invoices = Invoice.query.order_by(Invoice.id.desc()).all()
    all_customers = Customer.query.order_by(Customer.name.asc()).all()
    all_properties = Property.query.order_by(Property.address.asc()).all()
    return render_template(
        "invoices.html",
        invoices=all_invoices,
        customers=all_customers,
        properties=all_properties
    )


@app.route("/invoices/add", methods=["POST"])
@admin_required
def add_invoice():
    invoice = Invoice(
        customer_id=request.form.get("customer_id"),
        property_id=request.form.get("property_id") or None,
        invoice_number=request.form.get("invoice_number") or generate_invoice_number(),
        invoice_date=request.form.get("invoice_date") or datetime.now().strftime("%Y-%m-%d"),
        description=request.form.get("description"),
        amount=request.form.get("amount"),
        status=request.form.get("status"),
        notes=request.form.get("notes")
    )
    db.session.add(invoice)
    db.session.commit()
    flash("Invoice created.")
    return redirect(url_for("invoices"))


@app.route("/invoices/<int:invoice_id>")
@admin_required
def invoice_detail(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    return render_template("invoice_detail.html", invoice=invoice)


@app.route("/invoices/<int:invoice_id>/text")
@admin_required
def text_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    customer_phone = (invoice.customer.phone or "").strip()
    clean_phone = "".join(ch for ch in customer_phone if ch.isdigit())

    invoice_url = url_for("invoice_detail", invoice_id=invoice.id, _external=True)
    message = (
        f"Hello {invoice.customer.name}, this is Stephen with Toucan HVAC. "
        f"Here is your invoice #{invoice.invoice_number or invoice.id}: {invoice_url}"
    )

    sms_link = f"sms:{clean_phone}&body={quote(message)}" if clean_phone else None

    return render_template(
        "text_invoice.html",
        invoice=invoice,
        sms_link=sms_link,
        customer_phone=customer_phone
    )


@app.route("/invoices/<int:invoice_id>/email")
@admin_required
def email_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    customer_email = (invoice.customer.email or "").strip()
    invoice_url = url_for("invoice_detail", invoice_id=invoice.id, _external=True)

    subject = quote(f"Toucan HVAC Invoice #{invoice.invoice_number or invoice.id}")
    body = quote(
        f"Hello {invoice.customer.name},\n\n"
        f"Here is your invoice #{invoice.invoice_number or invoice.id}.\n"
        f"{invoice_url}\n\n"
        f"Thank you,\n"
        f"Stephen Oldham\n"
        f"Toucan HVAC\n"
        f"936-334-2944"
    )

    mailto_link = f"mailto:{customer_email}?subject={subject}&body={body}" if customer_email else None

    return render_template(
        "email_invoice.html",
        invoice=invoice,
        mailto_link=mailto_link,
        customer_email=customer_email
    )


@app.route("/jobs/<int:job_id>/create-invoice", methods=["POST"])
@admin_required
def create_invoice_from_job(job_id):
    job = Job.query.get_or_404(job_id)

    description_parts = []
    if job.job_type:
        description_parts.append(f"Job Type: {job.job_type}")
    if job.problem_reported:
        description_parts.append(f"Problem Reported: {job.problem_reported}")
    if job.diagnosis:
        description_parts.append(f"Diagnosis: {job.diagnosis}")
    if job.work_performed:
        description_parts.append(f"Work Performed: {job.work_performed}")
    if job.parts_used:
        description_parts.append(f"Parts Used: {job.parts_used}")
    if job.notes:
        description_parts.append(f"Notes: {job.notes}")

    invoice = Invoice(
        customer_id=job.customer_id,
        property_id=job.property_id,
        invoice_number=generate_invoice_number(),
        invoice_date=datetime.now().strftime("%Y-%m-%d"),
        description="\n".join(description_parts),
        amount=job.amount_charged or "0.00",
        status="Unpaid",
        notes=f"Created from Job #{job.id}"
    )
    db.session.add(invoice)

    job.status = "Billed"

    db.session.commit()
    flash("Invoice created from job.")
    return redirect(url_for("invoice_detail", invoice_id=invoice.id))



@app.route("/reset-admin-now")
def reset_admin_now():
    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(email="admin@toucanhvac.local").first()
        if not admin:
            admin = User(name="Stephen Oldham", email="admin@toucanhvac.local", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            return "Admin created"

        admin.set_password("admin123")
        db.session.commit()
        return "Admin reset"

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(email="admin@toucanhvac.local").first()
        if not admin:
            admin = User(name="Stephen Oldham", email="admin@toucanhvac.local", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

    app.run(debug=True, port=5001)
