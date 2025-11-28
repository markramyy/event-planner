from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from models import (
    create_event, get_event_by_id, get_organized_events, get_invited_events,
    delete_event, invite_user_to_event, update_rsvp_status, search_events,
    serialize_doc, get_user_by_id
)

events_bp = Blueprint('events', __name__)


@events_bp.route('/', methods=['POST'])
@jwt_required()
def create_new_event():
    """Create a new event"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate input
        required_fields = ['title', 'date', 'time', 'location', 'description']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'All fields are required'}), 400

        # Parse date
        try:
            event_date = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
        except Exception:
            return jsonify({'error': 'Invalid date format. Use ISO format (YYYY-MM-DD)'}), 400

        # Create event
        event = create_event(
            title=data['title'],
            description=data['description'],
            date=event_date,
            time=data['time'],
            location=data['location'],
            organizer_id=user_id
        )

        return jsonify({
            'message': 'Event created successfully',
            'event': serialize_doc(event)
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@events_bp.route('/organized', methods=['GET'])
@jwt_required()
def get_user_organized_events():
    """Get events organized by current user"""
    try:
        user_id = get_jwt_identity()
        events = get_organized_events(user_id)

        return jsonify({
            'events': [serialize_doc(event) for event in events]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@events_bp.route('/invited', methods=['GET'])
@jwt_required()
def get_user_invited_events():
    """Get events user is invited to"""
    try:
        user_id = get_jwt_identity()
        events = get_invited_events(user_id)

        return jsonify({
            'events': [serialize_doc(event) for event in events]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@events_bp.route('/<event_id>', methods=['GET'])
@jwt_required()
def get_event_details(event_id):
    """Get single event details"""
    try:
        user_id = get_jwt_identity()
        event = get_event_by_id(event_id)

        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Check if user is participant
        is_participant = any(
            str(p['user_id']) == user_id for p in event['participants']
        )

        if not is_participant:
            return jsonify({'error': 'Access denied'}), 403

        return jsonify({
            'event': serialize_doc(event)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@events_bp.route('/<event_id>', methods=['DELETE'])
@jwt_required()
def delete_user_event(event_id):
    """Delete an event (organizer only)"""
    try:
        user_id = get_jwt_identity()

        if delete_event(event_id, user_id):
            return jsonify({'message': 'Event deleted successfully'}), 200
        else:
            return jsonify({'error': 'Event not found or unauthorized'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@events_bp.route('/<event_id>/invite', methods=['POST'])
@jwt_required()
def invite_to_event(event_id):
    """Invite a user to an event"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if not data or not data.get('email'):
            return jsonify({'error': 'Email is required'}), 400

        # Check if current user is organizer
        event = get_event_by_id(event_id)
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        if str(event['organizer_id']) != user_id:
            return jsonify({'error': 'Only organizer can invite users'}), 403

        # Invite user
        invited_user, error = invite_user_to_event(event_id, data['email'])

        if error:
            return jsonify({'error': error}), 400

        return jsonify({
            'message': 'User invited successfully',
            'invited_user': {
                'id': str(invited_user['_id']),
                'email': invited_user['email'],
                'name': invited_user['name']
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@events_bp.route('/<event_id>/rsvp', methods=['PUT'])
@jwt_required()
def rsvp_to_event(event_id):
    """Update RSVP status for an event"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if not data or not data.get('status'):
            return jsonify({'error': 'Status is required'}), 400

        status = data['status']
        success, error = update_rsvp_status(event_id, user_id, status)

        if error:
            return jsonify({'error': error}), 400

        if not success:
            return jsonify({'error': 'Failed to update status or not invited'}), 400

        return jsonify({'message': 'RSVP status updated successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@events_bp.route('/<event_id>/attendees', methods=['GET'])
@jwt_required()
def get_event_attendees(event_id):
    """Get list of attendees for an event"""
    try:
        user_id = get_jwt_identity()
        event = get_event_by_id(event_id)

        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Check if user is organizer
        if str(event['organizer_id']) != user_id:
            return jsonify({'error': 'Only organizer can view attendees'}), 403

        # Get attendee details
        attendees = []
        for participant in event['participants']:
            user = get_user_by_id(str(participant['user_id']))
            if user:
                attendees.append({
                    'id': str(user['_id']),
                    'name': user['name'],
                    'email': user['email'],
                    'role': participant['role'],
                    'status': participant['status'],
                    'invited_at': participant['invited_at'].isoformat()
                })

        return jsonify({'attendees': attendees}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@events_bp.route('/search', methods=['GET'])
@jwt_required()
def search_user_events():
    """Search events with filters"""
    try:
        user_id = get_jwt_identity()

        # Get query parameters
        keyword = request.args.get('keyword')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        role = request.args.get('role')  # 'organizer' or 'attendee'

        # Parse dates
        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except Exception:
                return jsonify({'error': 'Invalid start_date format'}), 400

        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except Exception:
                return jsonify({'error': 'Invalid end_date format'}), 400

        # Search
        events = search_events(user_id, keyword, start_date, end_date, role)

        return jsonify({
            'events': [serialize_doc(event) for event in events]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
