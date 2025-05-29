import os
from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from models import Incident, User, StatusUpdate
from forms import IncidentForm
from utils import allowed_file, user_required
from mongo_utils import save_image, get_image_base64
from . import user_bp
from datetime import datetime

@user_bp.route('/dashboard')
@login_required
@user_required
def dashboard():
    # Get user's recent incidents
    recent_incidents = Incident.query.filter_by(reported_by=current_user.id)\
                                   .order_by(Incident.created_at.desc())\
                                   .limit(5).all()
    
    # Get statistics
    total_incidents = Incident.query.filter_by(reported_by=current_user.id).count()
    pending_incidents = Incident.query.filter_by(reported_by=current_user.id, status='pending').count()
    resolved_incidents = Incident.query.filter_by(reported_by=current_user.id, status='resolved').count()
    
    stats = {
        'total': total_incidents,
        'pending': pending_incidents,
        'in_progress': Incident.query.filter_by(reported_by=current_user.id, status='in_progress').count(),
        'resolved': resolved_incidents
    }
    
    return render_template('user/dashboard.html', 
                         recent_incidents=recent_incidents,
                         stats=stats)

@user_bp.route('/report-incident', methods=['GET', 'POST'])
@login_required
@user_required
def report_incident():
    # Check if user has any active incidents (pending or in_progress)
    active_incidents = Incident.query.filter_by(
        reported_by=current_user.id
    ).filter(
        Incident.status.in_(['pending', 'in_progress'])
    ).count()
    
    if active_incidents > 0:
        flash('You already have an active incident. You cannot report a new incident until your current one is resolved or closed.', 'error')
        return redirect(url_for('user.my_incidents'))
        
    form = IncidentForm()
    
    if form.validate_on_submit():
        try:
            # Validate incident_type against allowed values
            allowed_types = ['fire', 'medical', 'accident', 'natural_disaster', 'crime', 'utility', 'other']
            if form.incident_type.data not in allowed_types:
                incident_type = 'other'
            else:
                incident_type = form.incident_type.data
                
            # Create new incident first (to get the ID)
            incident = Incident(
                title=form.title.data,
                description=form.description.data,
                incident_type=incident_type,
                priority=form.priority.data,
                address=form.address.data,
                latitude=float(form.latitude.data) if form.latitude.data else None,
                longitude=float(form.longitude.data) if form.longitude.data else None,
                reported_by=current_user.id
            )
            
            db.session.add(incident)
            db.session.flush()  # Get ID without committing
            
            # Handle file upload to MongoDB
            if form.image.data:
                try:
                    image_id = save_image(form.image.data, incident.id)
                    if image_id:
                        # Use raw SQL to update the image_id to avoid attribute errors
                        from sqlalchemy import text
                        db.session.execute(
                            text("UPDATE incidents SET image_id = :image_id WHERE id = :incident_id"),
                            {"image_id": image_id, "incident_id": incident.id}
                        )
                except Exception as e:
                    current_app.logger.error(f"Image upload error: {str(e)}")
            db.session.commit()
            
            # Send incident report notification
            try:
                from email_utils import send_incident_report_notification
                notes = form.description.data
                send_incident_report_notification(incident, current_user, notes)
            except Exception as e:
                current_app.logger.error(f"Failed to send email notification: {str(e)}")
            
            flash('Incident reported successfully! Our team will respond shortly.', 'success')
            current_app.logger.info(f'New incident reported by {current_user.username}: {incident.title}')
            return redirect(url_for('user.my_incidents'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while reporting the incident. Please try again.', 'error')
            current_app.logger.error(f'Error reporting incident: {str(e)}')
    
    return render_template('user/report_incident.html', form=form)

@user_bp.route('/my-incidents')
@login_required
@user_required
def my_incidents():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    incidents = Incident.query.filter_by(reported_by=current_user.id)\
                             .order_by(Incident.created_at.desc())\
                             .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('user/my_incidents.html', incidents=incidents)

@user_bp.route('/incident/<int:incident_id>')
@login_required
@user_required
def view_incident(incident_id):
    incident = Incident.query.filter_by(id=incident_id, reported_by=current_user.id).first_or_404()
    
    # Get status updates for this incident
    status_updates = incident.status_updates.order_by(db.desc('created_at')).all()
    
    # Get image data if available
    from mongo_utils import get_image_base64
    image_data = None
    if incident.image_id:
        image_data = get_image_base64(incident.image_id)
    
    return render_template('user/incident_details.html', 
                         incident=incident,
                         status_updates=status_updates,
                         image_data=image_data)

@user_bp.route('/incident/<int:incident_id>/withdraw', methods=['POST'])
@login_required
@user_required
def withdraw_incident(incident_id):
    incident = Incident.query.filter_by(id=incident_id, reported_by=current_user.id).first_or_404()
    
    # Check if incident can be withdrawn (only pending status is allowed)
    if incident.status == 'in_progress':
        flash('Cannot withdraw incident when status is in progress.', 'error')
        return redirect(url_for('user.view_incident', incident_id=incident_id))
    elif incident.status not in ['pending']:
        flash(f'Cannot withdraw incident. Current status is {incident.status}.', 'error')
        return redirect(url_for('user.view_incident', incident_id=incident_id))
    
    try:
        old_status = incident.status
        incident.status = 'closed'
        
        # Create status update record
        status_update = StatusUpdate(
            incident_id=incident.id,
            old_status=old_status,
            new_status='closed',
            notes=f'Incident withdrawn by reporter: {current_user.full_name}',
            updated_by=current_user.id
        )
        
        db.session.add(status_update)
        db.session.commit()
        
        # Send notification to admin
        try:
            from email_utils import send_email
            admin_email = "vedanthh46@gmail.com"  # Use your admin email
            subject = f"Incident Withdrawn - #{incident.id}"
            
            message = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
                    .header {{ background-color: #dc3545; color: white; padding: 15px; text-align: center; border-radius: 5px 5px 0 0; }}
                    .content {{ padding: 20px; }}
                    .footer {{ background-color: #f5f5f5; padding: 10px; text-align: center; font-size: 12px; color: #666; }}
                    .alert-warning {{ background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 10px 0; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                    th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                    th {{ background-color: #f2f2f2; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Incident Withdrawn</h2>
                    </div>
                    <div class="content">
                        <div class="alert-warning">
                            <p>An incident has been withdrawn by the reporter:</p>
                        </div>
                        
                        <table>
                            <tr>
                                <th>ID</th>
                                <td>#{incident.id}</td>
                            </tr>
                            <tr>
                                <th>Title</th>
                                <td>{incident.title}</td>
                            </tr>
                            <tr>
                                <th>Type</th>
                                <td>{incident.incident_type.replace('_', ' ').title()}</td>
                            </tr>
                            <tr>
                                <th>Previous Status</th>
                                <td>{old_status.replace('_', ' ').title()}</td>
                            </tr>
                            <tr>
                                <th>Reported By</th>
                                <td>{current_user.full_name} ({current_user.email})</td>
                            </tr>
                        </table>
                        
                        <p>The incident has been automatically closed.</p>
                    </div>
                    <div class="footer">
                        <p>© 2025 Crisis Guardian. All rights reserved.</p>
                        <p>This is an automated message, please do not reply to this email.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            send_email(admin_email, subject, message)
        except Exception as e:
            current_app.logger.error(f"Failed to send withdrawal notification: {str(e)}")
        
        flash('Incident withdrawn successfully.', 'success')
        current_app.logger.info(f'Incident {incident.id} withdrawn by {current_user.username}')
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while withdrawing the incident. Please try again.', 'error')
        current_app.logger.error(f'Error withdrawing incident: {str(e)}')
    
    return redirect(url_for('user.my_incidents'))

@user_bp.route('/profile')
@login_required
@user_required
def profile():
    return render_template('user/profile.html')