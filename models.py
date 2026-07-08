from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Unified account table for Admin, Trek Staff, and Trekkers (Users)."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # role: 'admin', 'staff', 'user'
    role = db.Column(db.String(20), nullable=False, default="user")

    # For staff: needs admin approval before dashboard access.
    is_approved = db.Column(db.Boolean, default=False)

    # Blacklist flag applies to both staff and users.
    is_blacklisted = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    assigned_treks = db.relationship(
        "Trek", backref="staff", foreign_keys="Trek.assigned_staff_id"
    )
    bookings = db.relationship(
        "Booking", backref="trekker", foreign_keys="Booking.user_id"
    )

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_active(self):
        # Flask-Login active check: blacklisted accounts cannot log in.
        # Staff must also be approved.
        if self.is_blacklisted:
            return False
        if self.role == "staff" and not self.is_approved:
            return False
        return True

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Trek(db.Model):
    __tablename__ = "treks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)  # Easy / Moderate / Hard
    duration = db.Column(db.Integer, nullable=False)  # in days
    description = db.Column(db.Text, nullable=True)

    total_slots = db.Column(db.Integer, nullable=False, default=10)
    available_slots = db.Column(db.Integer, nullable=False, default=10)

    assigned_staff_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Status: Pending / Approved / Open / Closed / Completed
    status = db.Column(db.String(20), nullable=False, default="Pending")

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)

    price = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship("Booking", backref="trek", cascade="all, delete-orphan")

    @property
    def booked_count(self):
        return sum(1 for b in self.bookings if b.status == "Booked")

    def __repr__(self):
        return f"<Trek {self.name}>"


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey("treks.id"), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Status: Booked / Cancelled / Completed
    status = db.Column(db.String(20), nullable=False, default="Booked")

    def __repr__(self):
        return f"<Booking user={self.user_id} trek={self.trek_id}>"
