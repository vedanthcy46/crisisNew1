from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app import db
from models import User
from forms import LoginForm, RegistrationForm
from . import auth_bp

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_to_dashboard()
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        try:
            password_valid = check_password_hash(user.password_hash, form.password.data)
        except ValueError:
            # Handle scrypt hash format not supported in older Werkzeug
            flash('Authentication error. Please contact administrator.', 'error')
            current_app.logger.error(f'Password hash format not supported for user: {form.username.data}')
            return render_template('auth/login.html', form=form)
        
        if user and password_valid:
            if not user.is_active:
                flash('Your account has been deactivated. Please contact an administrator.', 'error')
                return render_template('auth/login.html', form=form)
            
            login_user(user)
            flash(f'Welcome back, {user.full_name}!', 'success')
            current_app.logger.info(f'User {user.username} logged in successfully')
            
            # Redirect to appropriate dashboard based on role
            return redirect_to_dashboard()
        else:
            flash('Invalid username or password.', 'error')
            current_app.logger.warning(f'Failed login attempt for username: {form.username.data}')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect_to_dashboard()
    
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            # Use sha256 method which is supported in older Werkzeug
            user = User(
                username=form.username.data,
                email=form.email.data,
                full_name=form.full_name.data,
                phone=form.phone.data,
                address=form.address.data,
                password_hash=generate_password_hash(form.password.data, method='sha256'),
                role='user'  # Default role for new registrations
            )
            
            db.session.add(user)
            db.session.commit()
            
            # Send registration confirmation email
            from email_utils import send_registration_confirmation
            send_registration_confirmation(user)
            
            flash('Registration successful! You can now log in.', 'success')
            current_app.logger.info(f'New user registered: {user.username}')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'error')
            current_app.logger.error(f'Registration error: {str(e)}')
    
    return render_template('auth/register.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    flash('You have been logged out successfully.', 'info')
    current_app.logger.info(f'User {username} logged out')
    return redirect(url_for('index'))

def redirect_to_dashboard():
    """Redirect user to appropriate dashboard based on their role"""
    if current_user.is_admin():
        return redirect(url_for('admin.dashboard'))
    elif current_user.is_rescue_team():
        return redirect(url_for('rescue.dashboard'))
    else:
        return redirect(url_for('user.dashboard'))