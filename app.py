import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix
import pymysql
pymysql.install_as_MySQLdb()
# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    # Create the app
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Configure the database
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "mysql://sql12781898:hbnGXtZDCQ@sql12.freesqldatabase.com:3306/sql12781898")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # File upload configuration
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Import models
    from models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    from auth import auth_bp
    from user import user_bp
    from rescue import rescue_bp
    from admin import admin_bp
    from routes import image_bp
    from chatbot import chatbot_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(rescue_bp, url_prefix='/rescue')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(image_bp, url_prefix='/media')
    app.register_blueprint(chatbot_bp)
    
    # Main route
    @app.route('/')
    def index():
        from flask import redirect, url_for, render_template
        from flask_login import current_user
        from auth.routes import redirect_to_dashboard
        
        if current_user.is_authenticated:
            return redirect_to_dashboard()
        return render_template('landing.html')
    
    # API endpoints for map data
    @app.route('/api/incidents')
    def api_incidents():
        from flask import jsonify
        from models import Incident, User
        
        incidents = Incident.query.all()
        incidents_data = []
        
        for incident in incidents:
            if incident.latitude and incident.longitude:
                assigned_team_name = None
                if incident.assigned_team_id:
                    team = User.query.get(incident.assigned_team_id)
                    if team:
                        assigned_team_name = team.full_name
                
                incidents_data.append({
                    'id': incident.id,
                    'title': incident.title,
                    'description': incident.description,
                    'incident_type': incident.incident_type,
                    'priority': incident.priority,
                    'status': incident.status,
                    'latitude': incident.latitude,
                    'longitude': incident.longitude,
                    'created_at': incident.created_at.isoformat(),
                    'assigned_team': assigned_team_name
                })
        
        return jsonify({'incidents': incidents_data})
    
    @app.route('/api/resources')
    def api_resources():
        from flask import jsonify
        from models import Resource
        
        resources = Resource.query.all()
        resources_data = []
        
        for resource in resources:
            # For demo, we'll add some mock coordinates based on resource location
            lat, lng = None, None
            if resource.location:
                # Simple coordinate assignment for demo (in real app, geocode the location)
                if 'north' in resource.location.lower():
                    lat, lng = 40.7589, -73.9851  # Central Park area
                elif 'south' in resource.location.lower():
                    lat, lng = 40.7505, -73.9934  # Times Square area
                elif 'east' in resource.location.lower():
                    lat, lng = 40.7614, -73.9776  # Upper East Side
                elif 'west' in resource.location.lower():
                    lat, lng = 40.7614, -73.9776  # Upper West Side
                else:
                    lat, lng = 40.7128, -74.0060  # Default NYC
            
            if lat and lng:
                resources_data.append({
                    'id': resource.id,
                    'name': resource.name,
                    'resource_type': resource.resource_type,
                    'availability_status': resource.availability_status,
                    'description': resource.description,
                    'location': resource.location,
                    'latitude': lat,
                    'longitude': lng
                })
        
        return jsonify({'resources': resources_data})
    
    # Profile route
    @app.route('/profile', methods=['GET', 'POST'])
    def profile():
        from flask import render_template, flash, redirect, request, url_for, current_app
        from flask_login import login_required, current_user
        from forms import ProfileForm
        from werkzeug.security import check_password_hash, generate_password_hash
        from datetime import datetime
        
        # Check if user is logged in
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        form = ProfileForm()
        
        # Pre-populate form with current user data
        if request.method == 'GET':
            form.username.data = current_user.username
            form.email.data = current_user.email
            form.full_name.data = current_user.full_name
            form.phone.data = current_user.phone
            form.address.data = current_user.address
        
        if form.validate_on_submit():
            # Check if new password was provided
            if form.new_password.data:
                if not form.current_password.data:
                    flash('Current password is required to change password.', 'error')
                    return render_template('profile.html', form=form)
                
                try:
                    password_valid = check_password_hash(current_user.password_hash, form.current_password.data)
                except ValueError:
                    flash('Password verification error. Please contact administrator.', 'error')
                    return render_template('profile.html', form=form)
                
                if not password_valid:
                    flash('Current password is incorrect.', 'error')
                    return render_template('profile.html', form=form)
                
                # Update password - use sha256 method which is supported in older Werkzeug
                current_user.password_hash = generate_password_hash(form.new_password.data, method='sha256')
            
            # Update profile information
            current_user.email = form.email.data
            current_user.full_name = form.full_name.data
            current_user.phone = form.phone.data
            current_user.address = form.address.data
            current_user.updated_at = datetime.utcnow()
            
            try:
                db.session.commit()
                flash('Profile updated successfully!', 'success')
                current_app.logger.info(f"Profile updated for user {current_user.username}")
            except Exception as e:
                db.session.rollback()
                flash('Error updating profile. Please try again.', 'error')
                current_app.logger.error(f'Error updating profile: {str(e)}')
            
            return redirect(url_for('profile'))
        
        return render_template('profile.html', form=form)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        
        # Create default admin user if it doesn't exist
        from models import User
        from werkzeug.security import generate_password_hash
        
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                email='admin@crisis.system',
                password_hash=generate_password_hash('admin123', method='sha256'),
                role='admin',
                full_name='System Administrator'
            )
            db.session.add(admin_user)
            db.session.commit()
            app.logger.info("Default admin user created: admin / admin123")
    
    return app

# Create app instance
app = create_app()
