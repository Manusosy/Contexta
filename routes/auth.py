"""Authentication routes — login and logout."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from models import db, User
import secrets
from utils.email_service import send_email

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    tier_id = request.args.get("tier")
    if tier_id:
        session["checkout_tier_id"] = tier_id

    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("dashboard.index"))
        t_id = session.pop("checkout_tier_id", None)
        if t_id:
            return redirect(url_for("client.checkout", tier_id=t_id))
        return redirect(url_for("client.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            # Security: only allow relative redirects
            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)
            # Role-based redirect
            if user.role == "admin":
                return redirect(url_for("dashboard.index"))
            return redirect(url_for("client.index"))

        flash("Invalid email or password.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    tier_id = request.args.get("tier")
    if tier_id:
        session["checkout_tier_id"] = tier_id

    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("dashboard.index"))
        t_id = session.pop("checkout_tier_id", None)
        if t_id:
            return redirect(url_for("client.checkout", tier_id=t_id))
        return redirect(url_for("client.index"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not password or not full_name:
            flash("Name, email, and password are required.", "error")
            return redirect(url_for("auth.register"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return redirect(url_for("auth.register"))

        # Create new user
        # Auto-generate a username from email prefix for internal compatibility
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(full_name=full_name, email=email, username=username, role="client")
        user.set_password(password)
        
        # Generate 6-digit verification code
        code = f"{secrets.randbelow(900000) + 100000}"
        user.verification_code = code
        user.is_verified = False
        
        db.session.add(user)
        db.session.commit()

        login_user(user)
        send_email(
            subject="Your Contexta Verification Code",
            recipient=email,
            body_text=f"Welcome to Contexta!\n\nYour verification code is: {code}\n\nThank you!"
        )
        flash("Registration successful. Please check your email for the verification code.", "success")
        return redirect(url_for("auth.verify_email"))

    return render_template("auth/register.html")

@auth_bp.route("/verify-email", methods=["GET", "POST"])
@login_required
def verify_email():
    if getattr(current_user, 'is_verified', True):
        flash("Email already verified.", "info")
        return redirect(url_for("client.index"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if code == current_user.verification_code:
            current_user.is_verified = True
            current_user.verification_code = None
            db.session.commit()
            flash("Email verified successfully! Welcome.", "success")
            if current_user.role == "admin":
                return redirect(url_for("dashboard.index"))
            
            if not current_user.onboarding_completed:
                return redirect(url_for("onboarding.index"))
            
            t_id = session.pop("checkout_tier_id", None)
            if t_id:
                return redirect(url_for("client.checkout", tier_id=t_id))
            return redirect(url_for("client.index"))
        
        flash("Invalid verification code. Please try again.", "error")

    return render_template("auth/verify.html")


@auth_bp.route("/resend-verification")
@login_required
def resend_verification():
    if getattr(current_user, 'is_verified', False):
        flash("Email already verified.", "info")
        return redirect(url_for("client.index"))
    
    # Generate new code
    code = f"{secrets.randbelow(900000) + 100000}"
    current_user.verification_code = code
    db.session.commit()
    
    send_email(
        subject="Your Contexta Verification Code",
        recipient=current_user.email,
        body_text=f"Your new Contexta verification code is: {code}"
    )
    flash(f"A new verification code has been sent to your email.", "success")
    return redirect(url_for("auth.verify_email"))


# ==========================================
# ADMIN AUTHENTICATION ROUTES
# ==========================================

@auth_bp.route("/admin-portal/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("client.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if user.role != "admin":
                flash("Access denied. Admin privileges required.", "error")
                return redirect(url_for("auth.admin_login"))
                
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)
                
            return redirect(url_for("dashboard.index"))

        flash("Invalid admin email or password.", "error")

    return render_template("auth/admin_login.html")


@auth_bp.route("/admin-portal/register", methods=["GET", "POST"])
def admin_register():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("client.index"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not password or not full_name:
            flash("Name, email, and password are required.", "error")
            return redirect(url_for("auth.admin_register"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth.admin_register"))
            
        # SECURITY RESTRICTION: Config-based or generic
        # Allowed Admin Domains logic will be handled via env variables if deemed necessary in production.
        pass

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return redirect(url_for("auth.admin_register"))

        base_username = email.split('@')[0]
        username = f"admin_{base_username}"
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"admin_{base_username}{counter}"
            counter += 1

        user = User(
            full_name=full_name, 
            email=email, 
            username=username,
            role="admin"  # Automatically an admin
        )
        user.set_password(password)
        
        # Generate 6-digit verification code
        code = f"{secrets.randbelow(900000) + 100000}"
        user.verification_code = code
        user.is_verified = False
        
        db.session.add(user)
        db.session.commit()

        login_user(user)
        send_email(
            subject="Your Contexta Admin Verification Code",
            recipient=email,
            body_text=f"Welcome Admin,\n\nYour verification code is: {code}\n\nPlease verify to access the dashboard."
        )
        flash("Admin registration successful. Verification required.", "success")
        return redirect(url_for("auth.verify_email"))

    return render_template("auth/admin_register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
