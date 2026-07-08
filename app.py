import os
from datetime import datetime, date
from functools import wraps

from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from models import db, User, Trek, Booking

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "trekking-management-secret-key-change-in-prod"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "trekking.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Access-control helpers
# ---------------------------------------------------------------------------
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public / Auth routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_router"))
    open_treks = (
        Trek.query.filter_by(status="Open")
        .order_by(Trek.start_date.asc())
        .limit(6)
        .all()
    )
    return render_template("index.html", open_treks=open_treks)


@app.route("/dashboard")
@login_required
def dashboard_router():
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if current_user.role == "staff":
        return redirect(url_for("staff_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_router"))

    if request.method == "POST":
        role = request.form.get("role", "user")
        if role not in ("user", "staff"):
            role = "user"

        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if not name or not username or not email or not password:
            errors.append("Please fill in all required fields.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if User.query.filter_by(username=username).first():
            errors.append("That username is already taken.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=request.form)

        new_user = User(
            name=name,
            username=username,
            email=email,
            phone=phone,
            role=role,
            is_approved=(role == "user"),  # users need no approval, staff do
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        if role == "staff":
            flash(
                "Registration successful! Your staff account is pending admin "
                "approval before you can log in.",
                "info",
            )
        else:
            flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_router"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("login.html")

        if user.is_blacklisted:
            flash("This account has been blacklisted. Contact the admin.", "danger")
            return render_template("login.html")

        if user.role == "staff" and not user.is_approved:
            flash("Your staff account is still awaiting admin approval.", "warning")
            return render_template("login.html")

        login_user(user)
        flash(f"Welcome back, {user.name}!", "success")
        return redirect(url_for("dashboard_router"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------
@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    stats = {
        "total_treks": Trek.query.count(),
        "total_users": User.query.filter_by(role="user").count(),
        "total_staff": User.query.filter_by(role="staff").count(),
        "total_bookings": Booking.query.count(),
        "pending_staff": User.query.filter_by(role="staff", is_approved=False, is_blacklisted=False).count(),
        "open_treks": Trek.query.filter_by(status="Open").count(),
    }
    recent_bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(5).all()
    return render_template("admin/dashboard.html", stats=stats, recent_bookings=recent_bookings)


@app.route("/admin/treks")
@role_required("admin")
def admin_treks():
    treks = Trek.query.order_by(Trek.created_at.desc()).all()
    return render_template("admin/treks.html", treks=treks)


@app.route("/admin/treks/new", methods=["GET", "POST"])
@role_required("admin")
def admin_trek_new():
    staff_list = User.query.filter_by(role="staff", is_approved=True, is_blacklisted=False).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        difficulty = request.form.get("difficulty", "Easy")
        duration = request.form.get("duration", type=int)
        total_slots = request.form.get("total_slots", type=int)
        description = request.form.get("description", "").strip()
        price = request.form.get("price", type=float) or 0.0
        staff_id = request.form.get("assigned_staff_id", type=int)
        start_date = parse_date(request.form.get("start_date"))
        end_date = parse_date(request.form.get("end_date"))

        if not name or not location or not duration or not total_slots:
            flash("Please fill in all required fields.", "danger")
            return render_template("admin/trek_form.html", trek=None, staff_list=staff_list, form=request.form)

        trek = Trek(
            name=name,
            location=location,
            difficulty=difficulty,
            duration=duration,
            total_slots=total_slots,
            available_slots=total_slots,
            description=description,
            price=price,
            assigned_staff_id=staff_id if staff_id else None,
            status="Approved" if staff_id else "Pending",
            start_date=start_date,
            end_date=end_date,
        )
        db.session.add(trek)
        db.session.commit()
        flash(f"Trek '{trek.name}' created successfully.", "success")
        return redirect(url_for("admin_treks"))

    return render_template("admin/trek_form.html", trek=None, staff_list=staff_list, form={})


@app.route("/admin/treks/<int:trek_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def admin_trek_edit(trek_id):
    trek = db.get_or_404(Trek, trek_id)
    staff_list = User.query.filter_by(role="staff", is_approved=True, is_blacklisted=False).all()

    if request.method == "POST":
        trek.name = request.form.get("name", "").strip()
        trek.location = request.form.get("location", "").strip()
        trek.difficulty = request.form.get("difficulty", "Easy")
        trek.duration = request.form.get("duration", type=int)
        new_total = request.form.get("total_slots", type=int)
        trek.description = request.form.get("description", "").strip()
        trek.price = request.form.get("price", type=float) or 0.0
        staff_id = request.form.get("assigned_staff_id", type=int)
        trek.start_date = parse_date(request.form.get("start_date"))
        trek.end_date = parse_date(request.form.get("end_date"))
        trek.status = request.form.get("status", trek.status)

        # Adjust available slots proportionally if total slots changed.
        if new_total is not None and new_total != trek.total_slots:
            diff = new_total - trek.total_slots
            trek.available_slots = max(0, trek.available_slots + diff)
            trek.total_slots = new_total

        if staff_id and staff_id != trek.assigned_staff_id:
            trek.assigned_staff_id = staff_id
            if trek.status == "Pending":
                trek.status = "Approved"

        db.session.commit()
        flash(f"Trek '{trek.name}' updated.", "success")
        return redirect(url_for("admin_treks"))

    return render_template("admin/trek_form.html", trek=trek, staff_list=staff_list, form={})


@app.route("/admin/treks/<int:trek_id>/delete", methods=["POST"])
@role_required("admin")
def admin_trek_delete(trek_id):
    trek = db.get_or_404(Trek, trek_id)
    db.session.delete(trek)
    db.session.commit()
    flash(f"Trek '{trek.name}' has been removed.", "info")
    return redirect(url_for("admin_treks"))


@app.route("/admin/staff")
@role_required("admin")
def admin_staff():
    staff = User.query.filter_by(role="staff").order_by(User.created_at.desc()).all()
    return render_template("admin/staff.html", staff=staff)


@app.route("/admin/staff/<int:staff_id>/approve", methods=["POST"])
@role_required("admin")
def admin_staff_approve(staff_id):
    staff = User.query.filter_by(id=staff_id, role="staff").first_or_404()
    staff.is_approved = True
    staff.is_blacklisted = False
    db.session.commit()
    flash(f"{staff.name} has been approved as trek staff.", "success")
    return redirect(url_for("admin_staff"))


@app.route("/admin/staff/<int:staff_id>/assign", methods=["POST"])
@role_required("admin")
def admin_staff_assign(staff_id):
    staff = User.query.filter_by(id=staff_id, role="staff").first_or_404()
    trek_id = request.form.get("trek_id", type=int)
    trek = db.get_or_404(Trek, trek_id)
    trek.assigned_staff_id = staff.id
    if trek.status == "Pending":
        trek.status = "Approved"
    db.session.commit()
    flash(f"{staff.name} assigned to '{trek.name}'.", "success")
    return redirect(url_for("admin_staff"))


@app.route("/admin/users")
@role_required("admin")
def admin_users():
    users = User.query.filter_by(role="user").order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@app.route("/admin/blacklist/<int:user_id>", methods=["POST"])
@role_required("admin")
def admin_toggle_blacklist(user_id):
    person = db.get_or_404(User, user_id)
    if person.role == "admin":
        abort(403)
    person.is_blacklisted = not person.is_blacklisted
    db.session.commit()
    state = "blacklisted" if person.is_blacklisted else "reinstated"
    flash(f"{person.name} has been {state}.", "warning" if person.is_blacklisted else "success")
    referrer = request.form.get("next") or url_for("admin_dashboard")
    return redirect(referrer)


@app.route("/admin/bookings")
@role_required("admin")
def admin_bookings():
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template("admin/bookings.html", bookings=bookings)


@app.route("/admin/search")
@role_required("admin")
def admin_search():
    query = request.args.get("q", "").strip()
    users, staff, treks = [], [], []
    if query:
        like = f"%{query}%"
        users = User.query.filter(
            User.role == "user",
            db.or_(User.name.ilike(like), User.username.ilike(like), User.email.ilike(like))
        ).all()
        staff = User.query.filter(
            User.role == "staff",
            db.or_(User.name.ilike(like), User.username.ilike(like), User.email.ilike(like))
        ).all()
        treks = Trek.query.filter(
            db.or_(Trek.name.ilike(like), Trek.location.ilike(like))
        ).all()
    return render_template("admin/search.html", query=query, users=users, staff=staff, treks=treks)


# ---------------------------------------------------------------------------
# Trek Staff routes
# ---------------------------------------------------------------------------
@app.route("/staff/dashboard")
@role_required("staff")
def staff_dashboard():
    treks = Trek.query.filter_by(assigned_staff_id=current_user.id).order_by(Trek.start_date.asc()).all()
    return render_template("staff/dashboard.html", treks=treks)


@app.route("/staff/trek/<int:trek_id>", methods=["GET", "POST"])
@role_required("staff")
def staff_trek_detail(trek_id):
    trek = db.get_or_404(Trek, trek_id)
    if trek.assigned_staff_id != current_user.id:
        abort(403)

    if request.method == "POST":
        new_total = request.form.get("total_slots", type=int)
        new_status = request.form.get("status")

        if new_total is not None and new_total != trek.total_slots:
            diff = new_total - trek.total_slots
            trek.available_slots = max(0, trek.available_slots + diff)
            trek.total_slots = new_total

        if new_status in ("Open", "Closed", "Completed", "Approved"):
            trek.status = new_status

        db.session.commit()
        flash("Trek details updated.", "success")
        return redirect(url_for("staff_trek_detail", trek_id=trek.id))

    participants = Booking.query.filter_by(trek_id=trek.id, status="Booked").all()
    return render_template("staff/trek_detail.html", trek=trek, participants=participants)


# ---------------------------------------------------------------------------
# User (Trekker) routes
# ---------------------------------------------------------------------------
@app.route("/user/dashboard")
@role_required("user")
def user_dashboard():
    my_bookings = (
        Booking.query.filter_by(user_id=current_user.id)
        .order_by(Booking.booking_date.desc())
        .limit(5)
        .all()
    )
    open_treks = Trek.query.filter_by(status="Open").order_by(Trek.start_date.asc()).limit(4).all()
    active_count = Booking.query.filter_by(user_id=current_user.id, status="Booked").count()
    return render_template(
        "user/dashboard.html",
        my_bookings=my_bookings,
        open_treks=open_treks,
        active_count=active_count,
    )


@app.route("/user/treks")
@role_required("user")
def user_treks():
    query = Trek.query.filter_by(status="Open")

    location = request.args.get("location", "").strip()
    difficulty = request.args.get("difficulty", "").strip()
    search = request.args.get("q", "").strip()

    if location:
        query = query.filter(Trek.location.ilike(f"%{location}%"))
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    if search:
        query = query.filter(Trek.name.ilike(f"%{search}%"))

    treks = query.order_by(Trek.start_date.asc()).all()

    my_trek_ids = {
        b.trek_id for b in Booking.query.filter_by(user_id=current_user.id, status="Booked").all()
    }

    return render_template(
        "user/treks.html",
        treks=treks,
        my_trek_ids=my_trek_ids,
        location=location,
        difficulty=difficulty,
        search=search,
    )


@app.route("/user/trek/<int:trek_id>")
@role_required("user")
def user_trek_detail(trek_id):
    trek = db.get_or_404(Trek, trek_id)
    already_booked = Booking.query.filter_by(
        user_id=current_user.id, trek_id=trek.id, status="Booked"
    ).first()
    return render_template("user/trek_detail.html", trek=trek, already_booked=already_booked)


@app.route("/user/book/<int:trek_id>", methods=["POST"])
@role_required("user")
def user_book_trek(trek_id):
    trek = db.get_or_404(Trek, trek_id)

    if trek.status != "Open":
        flash("This trek is not currently open for booking.", "danger")
        return redirect(url_for("user_treks"))

    if trek.available_slots <= 0:
        flash("Sorry, this trek is fully booked.", "danger")
        return redirect(url_for("user_trek_detail", trek_id=trek.id))

    existing = Booking.query.filter_by(
        user_id=current_user.id, trek_id=trek.id, status="Booked"
    ).first()
    if existing:
        flash("You have already booked this trek.", "info")
        return redirect(url_for("user_trek_detail", trek_id=trek.id))

    booking = Booking(user_id=current_user.id, trek_id=trek.id, status="Booked")
    trek.available_slots -= 1
    db.session.add(booking)
    db.session.commit()
    flash(f"Trek '{trek.name}' booked successfully! Happy trekking.", "success")
    return redirect(url_for("user_bookings"))


@app.route("/user/bookings")
@role_required("user")
def user_bookings():
    bookings = (
        Booking.query.filter_by(user_id=current_user.id)
        .order_by(Booking.booking_date.desc())
        .all()
    )
    return render_template("user/bookings.html", bookings=bookings)


@app.route("/user/bookings/<int:booking_id>/cancel", methods=["POST"])
@role_required("user")
def user_cancel_booking(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.user_id != current_user.id:
        abort(403)

    if booking.status == "Booked":
        booking.status = "Cancelled"
        booking.trek.available_slots += 1
        db.session.commit()
        flash("Booking cancelled.", "info")
    else:
        flash("This booking can no longer be cancelled.", "warning")

    return redirect(url_for("user_bookings"))


@app.route("/user/profile", methods=["GET", "POST"])
@role_required("user", "staff")
def user_profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", current_user.name).strip()
        current_user.phone = request.form.get("phone", current_user.phone).strip()
        new_password = request.form.get("password", "").strip()
        if new_password:
            current_user.set_password(new_password)
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("user_profile"))

    return render_template("user/profile.html")


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("errors.html", code=403, message="You don't have permission to access this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("errors.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("errors.html", code=500, message="Something went wrong on our end."), 500


# ---------------------------------------------------------------------------
# Database bootstrap: create tables + seed admin/sample data programmatically
# ---------------------------------------------------------------------------
def seed_database():
    db.create_all()

    if not User.query.filter_by(role="admin").first():
        admin = User(
            name="System Admin",
            username="admin",
            email="admin@trekmanage.com",
            phone="9999999999",
            role="admin",
            is_approved=True,
        )
        admin.set_password("admin123")
        db.session.add(admin)

    if not User.query.filter_by(username="staff_ravi").first():
        staff1 = User(
            name="Ravi Sharma",
            username="staff_ravi",
            email="ravi@trekmanage.com",
            phone="9876543210",
            role="staff",
            is_approved=True,
        )
        staff1.set_password("staff123")
        db.session.add(staff1)

    if not User.query.filter_by(username="staff_neha").first():
        staff2 = User(
            name="Neha Verma",
            username="staff_neha",
            email="neha@trekmanage.com",
            phone="9876500000",
            role="staff",
            is_approved=False,  # pending approval, to demo the approval flow
        )
        staff2.set_password("staff123")
        db.session.add(staff2)

    if not User.query.filter_by(username="trekker_amit").first():
        user1 = User(
            name="Amit Kumar",
            username="trekker_amit",
            email="amit@example.com",
            phone="9812345678",
            role="user",
            is_approved=True,
        )
        user1.set_password("user123")
        db.session.add(user1)

    db.session.commit()

    if Trek.query.count() == 0:
        ravi = User.query.filter_by(username="staff_ravi").first()
        treks = [
            Trek(
                name="Hampta Pass Trek",
                location="Himachal Pradesh",
                difficulty="Moderate",
                duration=5,
                total_slots=20,
                available_slots=14,
                description="A stunning crossover trek from the green Kullu valley to the "
                             "arid landscape of Lahaul, famous for dramatic terrain changes.",
                price=8500,
                assigned_staff_id=ravi.id,
                status="Open",
                start_date=date(2026, 8, 10),
                end_date=date(2026, 8, 15),
            ),
            Trek(
                name="Kedarkantha Trek",
                location="Uttarakhand",
                difficulty="Easy",
                duration=4,
                total_slots=25,
                available_slots=25,
                description="One of the best winter treks in India, offering panoramic "
                             "summit views of snow-capped Himalayan peaks.",
                price=6500,
                assigned_staff_id=ravi.id,
                status="Open",
                start_date=date(2026, 9, 5),
                end_date=date(2026, 9, 9),
            ),
            Trek(
                name="Roopkund Trek",
                location="Uttarakhand",
                difficulty="Hard",
                duration=8,
                total_slots=15,
                available_slots=15,
                description="A mysterious high-altitude glacial lake trek, known for its "
                             "skeletal remains and challenging terrain.",
                price=12000,
                assigned_staff_id=None,
                status="Pending",
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 9),
            ),
        ]
        db.session.add_all(treks)
        db.session.commit()


with app.app_context():
    seed_database()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
