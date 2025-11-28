from pymongo import MongoClient, ASCENDING, TEXT
from bson import ObjectId
from datetime import datetime
from config import Config

# MongoDB connection
client = MongoClient(Config.MONGO_URI)
db = client.get_database()

# Collections
users_collection = db['users']
events_collection = db['events']


# Create indexes
def init_db():
    """Initialize database indexes"""
    # User indexes
    users_collection.create_index([('email', ASCENDING)], unique=True)

    # Event indexes
    events_collection.create_index([('title', TEXT), ('description', TEXT)])
    events_collection.create_index([('date', ASCENDING)])
    events_collection.create_index([('organizer_id', ASCENDING)])

    print("Database indexes created successfully")


# Helper functions
def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    if doc is None:
        return None
    doc['_id'] = str(doc['_id'])
    if 'organizer_id' in doc:
        doc['organizer_id'] = str(doc['organizer_id'])
    if 'participants' in doc:
        for participant in doc['participants']:
            participant['user_id'] = str(participant['user_id'])
    return doc


def get_user_by_email(email):
    """Get user by email"""
    return users_collection.find_one({'email': email})


def get_user_by_id(user_id):
    """Get user by ID"""
    try:
        return users_collection.find_one({'_id': ObjectId(user_id)})
    except Exception:
        return None


def create_user(email, password_hash, name):
    """Create a new user"""
    user = {
        'email': email,
        'password': password_hash,
        'name': name,
        'created_at': datetime.utcnow()
    }
    result = users_collection.insert_one(user)
    user['_id'] = result.inserted_id
    return user


def create_event(title, description, date, time, location, organizer_id):
    """Create a new event"""
    event = {
        'title': title,
        'description': description,
        'date': date,
        'time': time,
        'location': location,
        'organizer_id': ObjectId(organizer_id),
        'created_at': datetime.utcnow(),
        'participants': [
            {
                'user_id': ObjectId(organizer_id),
                'role': 'organizer',
                'status': 'going',
                'invited_at': datetime.utcnow()
            }
        ]
    }
    result = events_collection.insert_one(event)
    event['_id'] = result.inserted_id
    return event


def get_event_by_id(event_id):
    """Get event by ID"""
    try:
        return events_collection.find_one({'_id': ObjectId(event_id)})
    except Exception:
        return None


def get_organized_events(user_id):
    """Get events organized by user"""
    try:
        return list(events_collection.find({'organizer_id': ObjectId(user_id)}))
    except Exception:
        return []


def get_invited_events(user_id):
    """Get events user is invited to (but not organizing)"""
    try:
        return list(events_collection.find({
            'participants.user_id': ObjectId(user_id),
            'organizer_id': {'$ne': ObjectId(user_id)}
        }))
    except Exception:
        return []


def delete_event(event_id, user_id):
    """Delete event if user is organizer"""
    try:
        result = events_collection.delete_one({
            '_id': ObjectId(event_id),
            'organizer_id': ObjectId(user_id)
        })
        return result.deleted_count > 0
    except Exception:
        return False


def invite_user_to_event(event_id, user_email):
    """Invite user to event"""
    user = get_user_by_email(user_email)
    if not user:
        return None, "User not found"

    event = get_event_by_id(event_id)
    if not event:
        return None, "Event not found"

    # Check if user already invited
    for participant in event['participants']:
        if participant['user_id'] == user['_id']:
            return None, "User already invited"

    # Add participant
    new_participant = {
        'user_id': user['_id'],
        'role': 'attendee',
        'status': None,
        'invited_at': datetime.utcnow()
    }

    events_collection.update_one(
        {'_id': ObjectId(event_id)},
        {'$push': {'participants': new_participant}}
    )

    return user, None


def update_rsvp_status(event_id, user_id, status):
    """Update user's RSVP status"""
    if status not in ['going', 'maybe', 'not_going']:
        return False, "Invalid status"

    try:
        result = events_collection.update_one(
            {
                '_id': ObjectId(event_id),
                'participants.user_id': ObjectId(user_id)
            },
            {
                '$set': {'participants.$.status': status}
            }
        )
        return result.modified_count > 0, None
    except Exception:
        return False, "Error updating status"


def search_events(user_id, keyword=None, start_date=None, end_date=None, role=None):
    """Search events with filters"""
    query = {'participants.user_id': ObjectId(user_id)}

    # Keyword search
    if keyword:
        query['$text'] = {'$search': keyword}

    # Date range
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query['$gte'] = start_date
        if end_date:
            date_query['$lte'] = end_date
        query['date'] = date_query

    # Role filter
    if role == 'organizer':
        query['organizer_id'] = ObjectId(user_id)
    elif role == 'attendee':
        query['organizer_id'] = {'$ne': ObjectId(user_id)}

    try:
        return list(events_collection.find(query))
    except Exception:
        return []
