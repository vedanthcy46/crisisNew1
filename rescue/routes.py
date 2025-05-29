from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app import db
from models import Incident, StatusUpdate
from forms import StatusUpdateForm, RescueStatusUpdateForm
from utils import rescue_team_required
from . import rescue_bp
from datetime import datetime

@rescue_bp.route('/dashboard')
@login_required
@rescue_team_required
def dashboard():
    # Get assigned incidents
    assigned_incidents = Incident.query.filter_by(assigned_team_id=current_user.id)\
                                      .order_by(Incident.created_at.desc())\
                                      .limit(10).all()
    
    # Get all unassigned incidents
    unassigned_incidents = Incident.query.filter_by(assigned_team_id=None)\
                                        .filter(Incident.status.in_(['pending', 'in_progress']))\
                                        .order_by(Incident.created_at.desc())\
                                        .limit(5).all()
    
    # Get statistics
    total_assigned = Incident.query.filter_by(assigned_team_id=current_user.id).count()
    pending_assigned = Incident.query.filter_by(assigned_team_id=current_user.id, status='pending').count()
    in_progress_assigned = Incident.query.filter_by(assigned_team_id=current_user.id, status='in_progress').count()
    resolved_assigned = Incident.query.filter_by(assigned_team_id=current_user.id, status='resolved').count()
    
    stats = {
        'total_assigned': total_assigned,
        'pending': pending_assigned,
        'in_progress': in_progress_assigned,
        'resolved': resolved_assigned
    }
    
    return render_template('rescue/dashboard.html',
                         assigned_incidents=assigned_incidents,
                         unassigned_incidents=unassigned_incidents,
                         stats=stats)

@rescue_bp.route('/incident/<int:incident_id>')
@login_required
@rescue_team_required
def incident_details(incident_id):
    # Rescue teams can view any incident, but can only update assigned ones
    incident = Incident.query.get_or_404(incident_id)
    
    # Get status updates for this incident
    status_updates = incident.status_updates.order_by(db.desc('created_at')).all()
    
    # Get image data if available
    from mongo_utils import get_image_base64
    image_data = None
    if incident.image_id:
        image_data = get_image_base64(incident.image_id)
    
    # Check if this incident is assigned to current user and not closed/rejected
    can_update = incident.assigned_team_id == current_user.id and incident.status not in ['closed', 'rejected']
    
    form = RescueStatusUpdateForm() if can_update else None
    
    # Dynamically set available status options based on current status
    if form and incident.status == 'in_progress':
        form.status.choices = [('resolved', 'Resolved')]
    elif form and incident.status == 'resolved':
        form.status.choices = [('closed', 'Closed')]
    
    return render_template('rescue/incident_details.html',
                         incident=incident,
                         status_updates=status_updates,
                         can_update=can_update,
                         form=form,
                         image_data=image_data)

@rescue_bp.route('/incident/<int:incident_id>/update-status', methods=['POST'])
@login_required
@rescue_team_required
def update_status(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    
    # Check if incident is already closed or rejected
    if incident.status in ['closed', 'rejected']:
        flash(f'Cannot update status. Incident is already {incident.status}.', 'error')
        return redirect(url_for('rescue.incident_details', incident_id=incident_id))
        
    # Validate that the new status follows the correct flow
    new_status = request.form.get('status')
    if incident.status == 'in_progress' and new_status != 'resolved':
        flash('Invalid status transition. From in_progress, you can only move to resolved.', 'error')
        return redirect(url_for('rescue.incident_details', incident_id=incident_id))
    elif incident.status == 'resolved' and new_status != 'closed':
        flash('Invalid status transition. From resolved, you can only move to closed.', 'error')
        return redirect(url_for('rescue.incident_details', incident_id=incident_id))
    
    # Check if incident is assigned to current user
    if incident.assigned_team_id != current_user.id:
        flash('You can only update incidents assigned to you.', 'error')
        return redirect(url_for('rescue.incident_details', incident_id=incident_id))
    
    form = RescueStatusUpdateForm()
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
            
            # If status is closed, handle image upload
            if new_status == 'closed' and form.image.data:
                from mongo_utils import save_image
                try:
                    rescue_image_id = save_image(form.image.data, incident.id)
                    if rescue_image_id:
                        incident.rescue_image_id = rescue_image_id
                        current_app.logger.info(f"Rescue image uploaded for incident {incident.id}")
                except Exception as e:
                    current_app.logger.error(f"Rescue image upload error: {str(e)}")
            
            # If status is resolved, closed or rejected, update any assigned resources to available
            if new_status in ['resolved', 'closed', 'rejected']:
                from models import IncidentResource, Resource
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
            
            # Send status update notification
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
    
    return redirect(url_for('rescue.incident_details', incident_id=incident_id))

@rescue_bp.route('/accept-incident/<int:incident_id>')
@login_required
@rescue_team_required
def accept_incident(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    
    # Check if incident is already closed, resolved or rejected
    if incident.status in ['closed', 'rejected', 'resolved', 'in_progress']:
        flash(f'Cannot accept incident. Incident is already {incident.status}.', 'error')
        return redirect(url_for('rescue.dashboard'))
    
    # Check if incident is unassigned
    if incident.assigned_team_id is not None:
        flash('This incident is already assigned to a team.', 'warning')
        return redirect(url_for('rescue.dashboard'))
    
    # Check if rescue team already has an active incident
    active_incidents = Incident.query.filter_by(
        assigned_team_id=current_user.id
    ).filter(
        Incident.status.in_(['pending', 'in_progress'])
    ).count()
    
    if active_incidents > 0:
        flash('You already have an active incident. You cannot accept another incident until your current one is resolved or closed.', 'error')
        return redirect(url_for('rescue.dashboard'))
    
    try:
        # Assign incident to current user
        incident.assigned_team_id = current_user.id
        if incident.status == 'pending':
            incident.status = 'in_progress'
        
        # Create status update record
        status_update = StatusUpdate(
            incident_id=incident.id,
            old_status='pending',
            new_status='in_progress',
            notes=f'Incident accepted by rescue team {current_user.full_name}',
            updated_by=current_user.id
        )
        
        db.session.add(status_update)
        db.session.commit()
        
        # Send notification to reporter
        try:
            from email_utils import send_status_update_notification
            reporter = incident.reporter
            send_status_update_notification(incident, 'pending', 'in_progress', reporter, current_user)
        except Exception as e:
            current_app.logger.error(f"Failed to send email notification: {str(e)}")
        
        flash(f'You have accepted incident: {incident.title}', 'success')
        current_app.logger.info(f'Incident {incident.id} accepted by {current_user.username}')
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while accepting the incident. Please try again.', 'error')
        current_app.logger.error(f'Error accepting incident: {str(e)}')
    
    return redirect(url_for('rescue.incident_details', incident_id=incident_id))

@rescue_bp.route('/my-incidents')
@login_required
@rescue_team_required
def my_incidents():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    incidents = Incident.query.filter_by(assigned_team_id=current_user.id)\
                             .order_by(Incident.created_at.desc())\
                             .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('rescue/my_incidents.html', incidents=incidents)
