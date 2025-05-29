import os
from datetime import datetime
from flask import render_template, request, flash, redirect, url_for, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from sqlalchemy import func, extract
from app import db
from models import User, Incident, Resource, IncidentResource, StatusUpdate
from forms import UserManagementForm, ResourceForm, AssignResourceForm, AssignTeamForm, StatusUpdateForm, AdminStatusUpdateForm
from utils import admin_required
from . import admin_bp

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # Get overall statistics
    total_users = User.query.filter_by(role='user').count()
    total_rescue_teams = User.query.filter_by(role='rescue_team').count()
    total_incidents = Incident.query.count()
    total_resources = Resource.query.count()
    
    # Get recent incidents
    recent_incidents = Incident.query.order_by(Incident.created_at.desc()).limit(5).all()
    
    # Get incidents by status
    incident_stats = {
        'pending': Incident.query.filter_by(status='pending').count(),
        'in_progress': Incident.query.filter_by(status='in_progress').count(),
        'resolved': Incident.query.filter_by(status='resolved').count(),
        'closed': Incident.query.filter_by(status='closed').count()
    }
    
    # Get high priority incidents
    high_priority_incidents = Incident.query.filter(
        Incident.priority.in_(['high', 'critical']),
        Incident.status.in_(['pending', 'in_progress'])
    ).count()
    
    stats = {
        'total_users': total_users,
        'total_rescue_teams': total_rescue_teams,
        'total_incidents': total_incidents,
        'total_resources': total_resources,
        'high_priority_incidents': high_priority_incidents,
        'incident_stats': incident_stats
    }
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_incidents=recent_incidents)

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    users = User.query.order_by(User.created_at.desc())\
                     .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = UserManagementForm()
    
    if form.validate_on_submit():
        try:
            # Skip validation for existing users in admin panel
            # Admin should be able to create users even if validation would normally fail
            
            user = User(
                username=form.username.data,
                email=form.email.data,
                full_name=form.full_name.data,
                phone=form.phone.data,
                address=form.address.data,
                role=form.role.data,
                password_hash=generate_password_hash(form.password.data or 'defaultpass123')
            )
            
            db.session.add(user)
            db.session.commit()
            
            # Send registration notification to the user
            try:
                from email_utils import send_registration_confirmation
                send_registration_confirmation(user)
                current_app.logger.info(f'Registration notification sent to {user.email}')
            except Exception as e:
                current_app.logger.error(f'Failed to send registration notification: {str(e)}')
            
            flash(f'User {user.username} created successfully.', 'success')
            current_app.logger.info(f'User {user.username} created by admin {current_user.username}')
            return redirect(url_for('admin.users'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the user. Please try again.', 'error')
            current_app.logger.error(f'Error creating user: {str(e)}')
    
    return render_template('admin/user_form.html', form=form, title='Add User')

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserManagementForm(obj=user)
    
    if form.validate_on_submit():
        try:
            user.username = form.username.data
            user.email = form.email.data
            user.full_name = form.full_name.data
            user.phone = form.phone.data
            user.address = form.address.data
            user.role = form.role.data
            
            if form.password.data:
                user.password_hash = generate_password_hash(form.password.data)
            
            db.session.commit()
            
            flash(f'User {user.username} updated successfully.', 'success')
            current_app.logger.info(f'User {user.username} updated by admin {current_user.username}')
            return redirect(url_for('admin.users'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the user. Please try again.', 'error')
            current_app.logger.error(f'Error updating user: {str(e)}')
    
    return render_template('admin/user_form.html', form=form, user=user, title='Edit User')

@admin_bp.route('/users/<int:user_id>/toggle-status')
@login_required
@admin_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.users'))
    
    try:
        user.is_active = not user.is_active
        db.session.commit()
        
        status = 'activated' if user.is_active else 'deactivated'
        flash(f'User {user.username} {status} successfully.', 'success')
        current_app.logger.info(f'User {user.username} {status} by admin {current_user.username}')
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while updating the user status. Please try again.', 'error')
        current_app.logger.error(f'Error toggling user status: {str(e)}')
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/rescue-teams')
@login_required
@admin_required
def rescue_teams():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    rescue_teams = User.query.filter_by(role='rescue_team')\
                            .order_by(User.created_at.desc())\
                            .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/rescue_teams.html', rescue_teams=rescue_teams)

@admin_bp.route('/resources')
@login_required
@admin_required
def resources():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    resources = Resource.query.order_by(Resource.created_at.desc())\
                             .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/resources.html', resources=resources)

@admin_bp.route('/resources/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_resource():
    form = ResourceForm()
    
    if form.validate_on_submit():
        try:
            resource = Resource(
                name=form.name.data,
                resource_type=form.resource_type.data,
                description=form.description.data,
                availability_status=form.availability_status.data,
                location=form.location.data
            )
            
            db.session.add(resource)
            db.session.commit()
            
            flash(f'Resource {resource.name} created successfully.', 'success')
            current_app.logger.info(f'Resource {resource.name} created by admin {current_user.username}')
            return redirect(url_for('admin.resources'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the resource. Please try again.', 'error')
            current_app.logger.error(f'Error creating resource: {str(e)}')
    
    return render_template('admin/resource_form.html', form=form, title='Add Resource')

@admin_bp.route('/resources/<int:resource_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    form = ResourceForm(obj=resource)
    
    if form.validate_on_submit():
        try:
            resource.name = form.name.data
            resource.resource_type = form.resource_type.data
            resource.description = form.description.data
            resource.availability_status = form.availability_status.data
            resource.location = form.location.data
            
            db.session.commit()
            
            flash(f'Resource {resource.name} updated successfully.', 'success')
            current_app.logger.info(f'Resource {resource.name} updated by admin {current_user.username}')
            return redirect(url_for('admin.resources'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the resource. Please try again.', 'error')
            current_app.logger.error(f'Error updating resource: {str(e)}')
    
    return render_template('admin/resource_form.html', form=form, resource=resource, title='Edit Resource')

@admin_bp.route('/incidents')
@login_required
@admin_required
def incidents():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    
    query = Incident.query
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    if priority_filter:
        query = query.filter_by(priority=priority_filter)
    
    incidents = query.order_by(Incident.created_at.desc())\
                    .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/incidents.html', 
                         incidents=incidents,
                         status_filter=status_filter,
                         priority_filter=priority_filter)

@admin_bp.route('/incidents/<int:incident_id>')
@login_required
@admin_required
def view_incident(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    status_updates = incident.status_updates.order_by(db.desc('created_at')).all()
    
    # Get image data if available
    from mongo_utils import get_image_base64
    image_data = None
    if incident.image_id:
        image_data = get_image_base64(incident.image_id)
    
    # Get available rescue teams (those without active incidents) and resources for assignment
    busy_team_ids = db.session.query(Incident.assigned_team_id).filter(
        Incident.status.in_(['pending', 'in_progress']),
        Incident.assigned_team_id.isnot(None)
    ).distinct()
    
    rescue_teams = User.query.filter_by(role='rescue_team', is_active=True).filter(
        ~User.id.in_(busy_team_ids)
    ).all()
    available_resources = Resource.query.filter_by(availability_status='available').all()
    
    # Forms for assignments
    assign_team_form = AssignTeamForm()
    assign_team_form.team_id.choices = [(t.id, f"{t.full_name} ({t.username})") for t in rescue_teams]
    
    assign_resource_form = AssignResourceForm()
    assign_resource_form.resource_ids.choices = [(r.id, f"{r.name} ({r.resource_type})") for r in available_resources]
    
    # Use AdminStatusUpdateForm for admin panel
    status_form = AdminStatusUpdateForm()
    
    # Dynamically set available status options based on current status
    if incident.status == 'pending':
        status_form.status.choices = [('rejected', 'Rejected')]
    
    return render_template('admin/incident_details.html',
                         incident=incident,
                         status_updates=status_updates,
                         assign_team_form=assign_team_form,
                         assign_resource_form=assign_resource_form,
                         status_form=status_form,
                         image_data=image_data)

@admin_bp.route('/incidents/<int:incident_id>/assign-team', methods=['POST'])
@login_required
@admin_required
def assign_team(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    
    # Check if incident is already closed or rejected
    if incident.status in ['closed', 'rejected']:
        flash(f'Cannot assign team. Incident is already {incident.status}.', 'error')
        return redirect(url_for('admin.view_incident', incident_id=incident_id))
    
    # Check if incident is already in progress or resolved
    if incident.status in ['in_progress', 'resolved']:
        flash(f'Cannot assign team. Incident is already {incident.status}.', 'error')
        return redirect(url_for('admin.view_incident', incident_id=incident_id))
        
    form = AssignTeamForm()
    
    # Populate choices
    rescue_teams = User.query.filter_by(role='rescue_team', is_active=True).all()
    form.team_id.choices = [(t.id, f"{t.full_name} ({t.username})") for t in rescue_teams]
    
    if form.validate_on_submit():
        try:
            old_team = incident.assigned_team
            old_status = incident.status
            incident.assigned_team_id = form.team_id.data
            
            # Update status to in_progress when team is assigned
            incident.status = 'in_progress'
            
            # Create status update
            team = User.query.get(form.team_id.data)
            notes = form.notes.data or f"Assigned to rescue team: {team.full_name}"
            
            status_update = StatusUpdate(
                incident_id=incident.id,
                old_status=old_status,
                new_status='in_progress',
                notes=notes,
                updated_by=current_user.id
            )
            
            db.session.add(status_update)
            db.session.commit()
            
            # Send notification to rescue team
            try:
                from email_utils import send_incident_assignment_notification
                send_incident_assignment_notification(incident, team)
            except Exception as e:
                current_app.logger.error(f"Failed to send email notification: {str(e)}")
            
            flash(f'Incident assigned to {team.full_name} successfully.', 'success')
            current_app.logger.info(f'Incident {incident.id} assigned to team {team.username} by admin {current_user.username}')
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while assigning the team. Please try again.', 'error')
            current_app.logger.error(f'Error assigning team: {str(e)}')
    
    return redirect(url_for('admin.view_incident', incident_id=incident_id))

@admin_bp.route('/incidents/<int:incident_id>/assign-resource', methods=['POST'])
@login_required
@admin_required
def assign_resource(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    
    # Check if incident is already closed or rejected
    if incident.status in ['closed', 'rejected']:
        flash(f'Cannot assign resources. Incident is already {incident.status}.', 'error')
        return redirect(url_for('admin.view_incident', incident_id=incident_id))
        
    form = AssignResourceForm()
    
    # Populate choices
    available_resources = Resource.query.filter_by(availability_status='available').all()
    form.resource_ids.choices = [(r.id, f"{r.name} ({r.resource_type})") for r in available_resources]
    
    if form.validate_on_submit():
        try:
            resource_id = form.resource_ids.data
            resource = Resource.query.get(resource_id)
            
            if resource:
                # Check if resource is already assigned to this incident
                existing_assignment = IncidentResource.query.filter_by(
                    incident_id=incident.id,
                    resource_id=resource.id,
                    released_at=None
                ).first()
                
                if not existing_assignment:
                    # Create resource assignment
                    assignment = IncidentResource(
                        incident_id=incident.id,
                        resource_id=resource.id,
                        notes=form.notes.data
                    )
                    
                    # Update resource status
                    resource.availability_status = 'in_use'
                    
                    db.session.add(assignment)
                    
                    # Create status update
                    notes = form.notes.data or f"Resource assigned: {resource.name}"
                    status_update = StatusUpdate(
                        incident_id=incident.id,
                        old_status=incident.status,
                        new_status=incident.status,
                        notes=notes,
                        updated_by=current_user.id
                    )
                    
                    db.session.add(status_update)
                    db.session.commit()
                    
                    flash(f'Resource {resource.name} assigned successfully!', 'success')
                    current_app.logger.info(f"Resource {resource.name} assigned to incident {incident.id} by {current_user.username}")
                else:
                    flash('This resource is already assigned to this incident.', 'warning')
            else:
                flash('Selected resource not found.', 'error')
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while assigning the resource. Please try again.', 'error')
            current_app.logger.error(f'Error assigning resource: {str(e)}')
    
    return redirect(url_for('admin.view_incident', incident_id=incident_id))

@admin_bp.route('/incidents/<int:incident_id>/update-status', methods=['POST'])
@login_required
@admin_required
def update_status(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    
    # Check if incident is already closed, resolved or rejected
    if incident.status in ['closed', 'rejected', 'resolved', 'in_progress']:
        flash(f'Cannot update status. Incident is already {incident.status}.', 'error')
        return redirect(url_for('admin.view_incident', incident_id=incident_id))
        
    # Validate that the new status follows the correct flow
    new_status = request.form.get('status')
    if incident.status == 'pending' and new_status != 'rejected':
        flash('Invalid status transition. From pending, you can only reject the incident.', 'error')
        return redirect(url_for('admin.view_incident', incident_id=incident_id))
        
    form = AdminStatusUpdateForm()
    
    if form.validate_on_submit():
        try:
            old_status = incident.status
            new_status = form.status.data
            
            # Create status update record
            status_update = StatusUpdate(
                incident_id=incident.id,
                old_status=old_status,
                new_status=new_status,
                notes=form.notes.data,
                updated_by=current_user.id
            )
            
            # Update incident status
            incident.status = new_status
            
            # If status is resolved, closed or rejected, update any assigned resources to available
            if new_status in ['resolved', 'closed', 'rejected']:
                # Get all resources assigned to this incident that haven't been released
                assigned_resources = IncidentResource.query.filter_by(
                    incident_id=incident.id,
                    released_at=None
                ).all()
                
                # Update each resource to available
                for assignment in assigned_resources:
                    resource = Resource.query.get(assignment.resource_id)
                    if resource:
                        resource.availability_status = 'available'
                        assignment.released_at = datetime.utcnow()
            
            db.session.add(status_update)
            db.session.commit()
            
            # Send notification to reporter
            try:
                from email_utils import send_status_update_notification
                reporter = incident.reporter
                send_status_update_notification(incident, old_status, new_status, reporter, current_user)
            except Exception as e:
                current_app.logger.error(f"Failed to send email notification: {str(e)}")
            
            flash(f'Incident status updated from "{old_status}" to "{new_status}".', 'success')
            current_app.logger.info(f'Incident {incident.id} status updated by {current_user.username}: {old_status} -> {new_status}')
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the status. Please try again.', 'error')
            current_app.logger.error(f'Error updating incident status: {str(e)}')
    
    return redirect(url_for('admin.view_incident', incident_id=incident_id))

@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    return render_template('admin/analytics.html')

@admin_bp.route('/api/analytics-data')
@login_required
@admin_required
def analytics_data():
    # Incidents by status
    status_data = db.session.query(
        Incident.status,
        func.count(Incident.id)
    ).group_by(Incident.status).all()
    
    # Incidents by type
    type_data = db.session.query(
        Incident.incident_type,
        func.count(Incident.id)
    ).group_by(Incident.incident_type).all()
    
    # Incidents by priority
    priority_data = db.session.query(
        Incident.priority,
        func.count(Incident.id)
    ).group_by(Incident.priority).all()
    
    # Monthly incident trends (last 12 months)
    monthly_data = db.session.query(
        extract('year', Incident.created_at).label('year'),
        extract('month', Incident.created_at).label('month'),
        func.count(Incident.id).label('count')
    ).group_by('year', 'month').order_by('year', 'month').limit(12).all()
    
    return jsonify({
        'status_distribution': {
            'labels': [item[0].title() for item in status_data],
            'data': [item[1] for item in status_data]
        },
        'type_distribution': {
            'labels': [item[0].replace('_', ' ').title() for item in type_data],
            'data': [item[1] for item in type_data]
        },
        'priority_distribution': {
            'labels': [item[0].title() for item in priority_data],
            'data': [item[1] for item in priority_data]
        },
        'monthly_trends': {
            'labels': [f"{int(item[1])}/{int(item[0])}" for item in monthly_data],
            'data': [item[2] for item in monthly_data]
        }
    })

# Delete functionality for all entities
@admin_bp.route('/delete/user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users'))
    
    try:
        # Store user info before deletion for email notification
        username = user.username
        email = user.email
        full_name = user.full_name
        
        db.session.delete(user)
        db.session.commit()
        
        # Send deletion notification to the user
        try:
            from email_utils import send_email
            subject = "Your Crisis Guardian Account Has Been Deleted"
            message = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
                    .header {{ background-color: #dc3545; color: white; padding: 15px; text-align: center; border-radius: 5px 5px 0 0; }}
                    .content {{ padding: 20px; }}
                    .footer {{ background-color: #f5f5f5; padding: 10px; text-align: center; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Account Deletion Notice</h2>
                    </div>
                    <div class="content">
                        <p>Hello {full_name},</p>
                        <p>This is to inform you that your Crisis Guardian account ({username}) has been deleted by an administrator.</p>
                        <p>If you believe this was done in error, please contact the system administrator.</p>
                        <p>Thank you for using Crisis Guardian.</p>
                    </div>
                    <div class="footer">
                        <p>© 2025 Crisis Guardian. All rights reserved.</p>
                        <p>This is an automated message, please do not reply to this email.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            send_email(email, subject, message)
            current_app.logger.info(f'Deletion notification sent to {email}')
        except Exception as e:
            current_app.logger.error(f'Failed to send deletion notification: {str(e)}')
        
        flash(f'User {username} deleted successfully.', 'success')
        current_app.logger.info(f"User {username} deleted by admin {current_user.username}")
    except Exception as e:
        db.session.rollback()
        flash('Error deleting user. User may have associated records.', 'error')
        current_app.logger.error(f'Error deleting user: {str(e)}')
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/delete/rescue-team/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_rescue_team(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.role != 'rescue_team':
        flash('This user is not a rescue team.', 'error')
        return redirect(url_for('admin.rescue_teams'))
    
    try:
        # Check if team has assigned incidents
        assigned_incidents = Incident.query.filter_by(assigned_team_id=user.id).count()
        if assigned_incidents > 0:
            flash(f'Cannot delete rescue team. They have {assigned_incidents} assigned incidents.', 'error')
            return redirect(url_for('admin.rescue_teams'))
        
        db.session.delete(user)
        db.session.commit()
        flash(f'Rescue team {user.full_name} deleted successfully.', 'success')
        current_app.logger.info(f"Rescue team {user.username} deleted by admin {current_user.username}")
    except Exception as e:
        db.session.rollback()
        flash('Error deleting rescue team.', 'error')
        current_app.logger.error(f'Error deleting rescue team: {str(e)}')
    
    return redirect(url_for('admin.rescue_teams'))

@admin_bp.route('/delete/resource/<int:resource_id>', methods=['POST'])
@login_required
@admin_required
def delete_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    
    try:
        db.session.delete(resource)
        db.session.commit()
        flash(f'Resource {resource.name} deleted successfully.', 'success')
        current_app.logger.info(f"Resource {resource.name} deleted by admin {current_user.username}")
    except Exception as e:
        db.session.rollback()
        flash('Error deleting resource. Resource may be assigned to incidents.', 'error')
        current_app.logger.error(f'Error deleting resource: {str(e)}')
    
    return redirect(url_for('admin.resources'))

@admin_bp.route('/delete/incident/<int:incident_id>', methods=['POST'])
@login_required
@admin_required
def delete_incident(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    
    try:
        # Delete associated images from MongoDB if they exist
        if incident.image_id:
            from mongo_utils import delete_image
            delete_image(incident.image_id)
            
        if incident.rescue_image_id:
            from mongo_utils import delete_image
            delete_image(incident.rescue_image_id)
        
        # Delete incident
        db.session.delete(incident)
        db.session.commit()
        flash(f'Incident {incident.title} deleted successfully.', 'success')
        current_app.logger.info(f"Incident {incident.title} deleted by admin {current_user.username}")
    except Exception as e:
        db.session.rollback()
        flash('Error deleting incident.', 'error')
        current_app.logger.error(f'Error deleting incident: {str(e)}')
    
    return redirect(url_for('admin.incidents'))

@admin_bp.route('/release/resource/<int:assignment_id>', methods=['POST'])
@login_required
@admin_required
def release_resource(assignment_id):
    assignment = IncidentResource.query.get_or_404(assignment_id)
    
    # Check if the incident is closed or rejected
    incident = Incident.query.get(assignment.incident_id)
    if incident.status in ['closed', 'rejected']:
        flash(f'Cannot release resources. Incident is already {incident.status}.', 'error')
        return redirect(url_for('admin.view_incident', incident_id=assignment.incident_id))
    
    try:
        # Mark assignment as released
        assignment.released_at = datetime.utcnow()
        
        # Update resource availability
        resource = Resource.query.get(assignment.resource_id)
        resource.availability_status = 'available'
        
        db.session.commit()
        flash(f'Resource {resource.name} released successfully.', 'success')
        current_app.logger.info(f"Resource {resource.name} released from incident {assignment.incident_id} by admin {current_user.username}")
    except Exception as e:
        db.session.rollback()
        flash('Error releasing resource.', 'error')
        current_app.logger.error(f'Error releasing resource: {str(e)}')
    
    return redirect(url_for('admin.view_incident', incident_id=assignment.incident_id))