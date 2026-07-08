# TrekManage — Trekking Management Application

A full-stack web app for managing trek approvals, staff assignment, and
bookings, built for Admin, Trek Staff, and User (Trekker) roles.

## Tech Stack
- **Backend:** Flask (Python)
- **Frontend:** Jinja2 templates + HTML + CSS + Bootstrap 5 (no JS used for
  core logic — only Bootstrap's own UI behaviors like the navbar toggle and
  optional confirm() dialogs on delete/cancel buttons)
- **Database:** SQLite, created programmatically via SQLAlchemy models
  (`db.create_all()` in `app.py` — no manual DB Browser usage)
- **Auth:** Flask-Login with hashed passwords (Werkzeug)

## Setup & Run

```bash
# 1. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app (the SQLite DB + seed data are created automatically
#    on first run — nothing to set up manually)
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## Demo Accounts (seeded automatically)

| Role   | Username      | Password  | Notes                          |
|--------|---------------|-----------|---------------------------------|
| Admin  | `admin`       | admin123  | Pre-existing superuser          |
| Staff  | `staff_ravi`  | staff123  | Approved, has 2 assigned treks  |
| Staff  | `staff_neha`  | staff123  | Pending admin approval (demo)   |
| User   | `trekker_amit`| user123   | Existing trekker account        |

You can also register new Trekker or Trek Staff accounts from the
**Sign Up** page. Staff accounts require admin approval before they can log in.

## Project Structure

```
trekking_management/
├── app.py                  # Routes, auth, business logic, DB bootstrap/seed
├── models.py                # SQLAlchemy models: User, Trek, Booking
├── requirements.txt
├── static/css/style.css     # Custom responsive styling (Bootstrap-based)
└── templates/
    ├── base.html            # Shared layout, navbar, flash messages
    ├── index.html, login.html, register.html, errors.html
    ├── admin/                # Admin dashboard, trek CRUD, staff/user mgmt, search
    ├── staff/                # Staff dashboard, trek detail/update, participants
    └── user/                 # User dashboard, browse/book treks, bookings, profile
```

## Core Features Implemented
- Role-based authentication (Admin pre-seeded, Staff/User self-register)
- Staff registration requires admin approval before dashboard access
- Admin: create/edit/delete treks, approve & assign staff, view all
  users/staff/treks, search by name, blacklist users/staff
- Staff: view assigned treks, update available slots & status, view
  registered participants per trek
- User: browse/search/filter open treks (by location & difficulty), book
  treks, view booking status & history, cancel bookings, edit profile
- Overbooking prevention — slots are checked and decremented atomically
  within the booking route; a trek at 0 available slots cannot be booked
- Only the staff member assigned to a trek can manage it (403 otherwise)
- Users can only book treks with status `Open`
- Full booking history retained (Booked / Cancelled / Completed)
