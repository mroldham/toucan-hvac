from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

customers = []

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/customers")
def customers_page():
    return render_template("customers.html", customers=customers)

@app.route("/customers/new", methods=["GET", "POST"])
def new_customer():
    if request.method == "POST":
        customers.append({
            "first_name": request.form.get("first_name", ""),
            "last_name": request.form.get("last_name", ""),
            "phone": request.form.get("phone", ""),
            "email": request.form.get("email", ""),
            "address": request.form.get("address", ""),
        })
        return redirect(url_for("customers_page"))
    return render_template("new_customer.html")

@app.route("/invoices")
def invoices():
    return render_template("invoice.html")

if __name__ == "__main__":
    app.run(debug=True, port=5001)
