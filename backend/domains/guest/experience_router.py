"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core.cache import cached
from core.database import db
from core.security import get_current_user
from models.schemas import (
    CreateDepartmentFeedbackRequest,
    CreateSurveyRequest,
    ExternalReviewWebhookRequest,
    SubmitSurveyResponseRequest,
    User,
)

router = APIRouter(prefix="/api", tags=["guest-experience"])

# ============= PHASE H: GUEST CRM + UPSELL AI + MESSAGING =============

@router.get("/crm/guest/{guest_id}")
async def get_guest_360(
    guest_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get 360° guest profile with all data"""
    # Get guest basic info
    guest = await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    # Get all bookings
    bookings = await db.bookings.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('check_in', -1).to_list(100)

    # Calculate stats
    total_stays = len([b for b in bookings if b['status'] in ['checked_out', 'checked_in']])
    total_nights = 0
    lifetime_value = 0.0
    adr_values = []

    for booking in bookings:
        if booking['status'] in ['checked_out', 'checked_in', 'confirmed']:
            nights = (datetime.fromisoformat(booking['check_out']) - datetime.fromisoformat(booking['check_in'])).days
            total_nights += nights
            lifetime_value += booking.get('total_amount', 0)
            if nights > 0:
                adr_values.append(booking.get('total_amount', 0) / nights)

    average_adr = sum(adr_values) / len(adr_values) if adr_values else 0

    # Get preferences
    preferences = await db.guest_preferences.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    # Get behavior
    behavior = await db.guest_behavior.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    # Get profile or create one
    profile = await db.guest_profiles.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not profile:
        # Create profile
        profile = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'guest_id': guest_id,
            'first_name': guest.get('name', '').split()[0] if guest.get('name') else '',
            'last_name': ' '.join(guest.get('name', '').split()[1:]) if guest.get('name') and len(guest.get('name', '').split()) > 1 else '',
            'email': guest.get('email'),
            'phone': guest.get('phone'),
            'country': guest.get('country'),
            'total_stays': total_stays,
            'total_nights': total_nights,
            'lifetime_value': round(lifetime_value, 2),
            'average_adr': round(average_adr, 2),
            'loyalty_status': guest.get('loyalty_tier', 'standard'),
            'last_seen_date': bookings[0]['check_in'] if bookings else None,
            'tags': guest.get('tags', []),
            'notes': guest.get('notes', []),
            'created_at': datetime.now(UTC).isoformat(),
            'updated_at': datetime.now(UTC).isoformat()
        }
        await db.guest_profiles.insert_one(profile)

    # Channel distribution
    channel_mix = {}
    for booking in bookings:
        channel = booking.get('ota_channel') or 'direct'
        channel_mix[channel] = channel_mix.get(channel, 0) + 1

    # Recent upsells
    upsell_offers = await db.upsell_offers.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('created_at', -1).to_list(10)

    return {
        'guest': guest,
        'profile': profile,
        'preferences': preferences,
        'behavior': behavior,
        'stats': {
            'total_stays': total_stays,
            'total_nights': total_nights,
            'lifetime_value': round(lifetime_value, 2),
            'average_adr': round(average_adr, 2),
            'channel_distribution': channel_mix
        },
        'recent_bookings': bookings[:10],
        'recent_upsells': upsell_offers
    }

@router.post("/crm/guest/add-tag")
async def add_guest_tag(
    guest_id: str,
    tag: str,
    current_user: User = Depends(get_current_user)
):
    """Add tag to guest"""
    result = await db.guests.update_one(
        {'id': guest_id, 'tenant_id': current_user.tenant_id},
        {'$addToSet': {'tags': tag}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Guest not found")

    return {'message': f'Tag "{tag}" added successfully'}

@router.post("/crm/guest/note")
async def add_guest_note(
    guest_id: str,
    note: str,
    current_user: User = Depends(get_current_user)
):
    """Add note to guest"""
    note_obj = {
        'text': note,
        'created_by': current_user.name,
        'created_at': datetime.now(UTC).isoformat()
    }

    result = await db.guests.update_one(
        {'id': guest_id, 'tenant_id': current_user.tenant_id},
        {'$push': {'notes': note_obj}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Guest not found")

    return {'message': 'Note added successfully', 'note': note_obj}


@router.delete("/crm/guest/note")
async def delete_guest_note(
    guest_id: str,
    note_index: int,
    current_user: User = Depends(get_current_user)
):
    guest = await db.guests.find_one({'id': guest_id, 'tenant_id': current_user.tenant_id})
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    notes = guest.get('notes', [])
    if note_index < 0 or note_index >= len(notes):
        raise HTTPException(status_code=400, detail="Invalid note index")
    notes.pop(note_index)
    await db.guests.update_one(
        {'id': guest_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'notes': notes}}
    )
    return {'message': 'Note deleted successfully'}


@router.post("/ai/upsell/generate")
async def generate_upsell_offers(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """AI-powered upsell offer generation"""
    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get guest info
    guest = await db.guests.find_one({
        'id': booking['guest_id'],
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    # Get room info
    room = await db.rooms.find_one({
        'id': booking['room_id'],
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    offers = []

    # 1. Room Upgrade Logic
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    better_rooms = [r for r in rooms if r['base_price'] > room['base_price']]

    for better_room in better_rooms[:3]:  # Top 3 upgrades
        # Check availability
        check_in = booking['check_in']
        check_out = booking['check_out']

        conflicts = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'room_id': better_room['id'],
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
            'check_in': {'$lt': check_out},
            'check_out': {'$gt': check_in}
        })

        if conflicts == 0:
            # Calculate confidence
            loyalty_tier = guest.get('loyalty_tier', 'standard')
            confidence = 0.5

            if loyalty_tier == 'vip':
                confidence = 0.9
            elif loyalty_tier == 'gold':
                confidence = 0.75
            elif loyalty_tier == 'silver':
                confidence = 0.6

            # Check historical acceptance
            past_bookings = await db.bookings.count_documents({
                'guest_id': booking['guest_id'],
                'tenant_id': current_user.tenant_id,
                'status': 'checked_out'
            })

            if past_bookings > 5:
                confidence += 0.1

            confidence = min(0.95, confidence)

            price_diff = better_room['base_price'] - room['base_price']
            nights = (datetime.fromisoformat(check_out) - datetime.fromisoformat(check_in)).days
            total_upgrade_cost = price_diff * nights

            offers.append({
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'guest_id': booking['guest_id'],
                'booking_id': booking_id,
                'type': 'room_upgrade',
                'current_item': room['room_type'],
                'target_item': better_room['room_type'],
                'price': round(total_upgrade_cost, 2),
                'confidence': round(confidence, 2),
                'reason': f"{loyalty_tier.upper()} guest, {better_room['room_type']} available, strong demand",
                'valid_until': (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                'status': 'pending',
                'created_at': datetime.now(UTC).isoformat()
            })

    # 2. Early Check-in (if arrival is tomorrow or later)
    arrival_date = datetime.fromisoformat(check_in).date()
    today = datetime.now(UTC).date()

    if arrival_date > today:
        offers.append({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'guest_id': booking['guest_id'],
            'booking_id': booking_id,
            'type': 'early_checkin',
            'current_item': 'Standard 3PM check-in',
            'target_item': 'Early 12PM check-in',
            'price': 25.00,
            'confidence': 0.65,
            'reason': 'High-value amenity, low cost to hotel',
            'valid_until': (datetime.fromisoformat(check_in) - timedelta(days=1)).isoformat(),
            'status': 'pending',
            'created_at': datetime.now(UTC).isoformat()
        })

    # 3. Late Checkout
    offers.append({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': booking['guest_id'],
        'booking_id': booking_id,
        'type': 'late_checkout',
        'current_item': 'Standard 11AM checkout',
        'target_item': 'Late 2PM checkout',
        'price': 35.00,
        'confidence': 0.70,
        'reason': 'Popular add-on, high guest satisfaction',
        'valid_until': (datetime.fromisoformat(check_out) - timedelta(days=1)).isoformat(),
        'status': 'pending',
        'created_at': datetime.now(UTC).isoformat()
    })

    # 4. Airport Transfer
    offers.append({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': booking['guest_id'],
        'booking_id': booking_id,
        'type': 'airport_transfer',
        'current_item': None,
        'target_item': 'Premium airport transfer',
        'price': 50.00,
        'confidence': 0.55,
        'reason': 'Convenience add-on, good margin',
        'valid_until': (datetime.fromisoformat(check_in) - timedelta(days=1)).isoformat(),
        'status': 'pending',
        'created_at': datetime.now(UTC).isoformat()
    })

    # Sort by confidence
    offers.sort(key=lambda x: x['confidence'], reverse=True)

    # Save offers
    if offers:
        await db.upsell_offers.insert_many(offers)

    estimated_revenue = sum(o['price'] * o['confidence'] for o in offers)

    return {
        'booking_id': booking_id,
        'guest_name': guest.get('name', 'Unknown'),
        'offers': offers,
        'total_offers': len(offers),
        'estimated_revenue': round(estimated_revenue, 2)
    }

async def check_rate_limit(tenant_id: str, channel: str, limit_per_hour: int = 100) -> bool:
    """Check if rate limit is exceeded for messaging"""
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    count = await db.messages.count_documents({
        'tenant_id': tenant_id,
        'channel': channel,
        'sent_at': {'$gte': one_hour_ago}
    })

    return count < limit_per_hour

@router.post("/messages/send-email")
async def send_email(
    recipient: str,
    subject: str,
    body: str,
    guest_id: str | None = None,
    template_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Send email message with rate limiting"""
    # Check rate limit (100 emails per hour)
    if not await check_rate_limit(current_user.tenant_id, 'email', limit_per_hour=100):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 100 emails per hour. Please try again later."
        )

    # Validate email format
    if not recipient or '@' not in recipient:
        raise HTTPException(status_code=400, detail="Invalid email address")

    # Validate message body
    if not body or len(body.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    message = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'channel': 'email',
        'recipient': recipient,
        'subject': subject,
        'body': body,
        'template_id': template_id,
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id,
        'status': 'sent'
    }

    await db.messages.insert_one(message)

    return {
        'message': 'Email sent successfully',
        'message_id': message['id'],
        'recipient': recipient,
        'rate_limit': {
            'limit': 100,
            'window': '1 hour',
            'remaining': 100 - await db.messages.count_documents({
                'tenant_id': current_user.tenant_id,
                'channel': 'email',
                'sent_at': {'$gte': (datetime.now(UTC) - timedelta(hours=1)).isoformat()}
            })
        }
    }

@router.post("/messages/send-sms")
async def send_sms(
    recipient: str,
    body: str,
    guest_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Send SMS message with stricter rate limiting (50 per hour)"""
    # SMS has stricter rate limit due to cost
    if not await check_rate_limit(current_user.tenant_id, 'sms', limit_per_hour=50):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 50 SMS per hour. Please try again later."
        )

    # Validate phone number format
    if not recipient or not recipient.startswith('+'):
        raise HTTPException(status_code=400, detail="Invalid phone number format. Must start with + and country code")

    # Validate message body
    if not body or len(body.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    # Warn if message is too long for single SMS
    if len(body) > 160:
        message_warning = f"Message is {len(body)} characters. Will be sent as {(len(body) // 160) + 1} SMS segments."
    else:
        message_warning = None

    message = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'channel': 'sms',
        'recipient': recipient,
        'body': body,
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id,
        'status': 'sent',
        'character_count': len(body),
        'segment_count': (len(body) // 160) + 1
    }

    await db.messages.insert_one(message)

    response = {
        'message': 'SMS sent successfully',
        'message_id': message['id'],
        'recipient': recipient,
        'character_count': len(body),
        'segments': (len(body) // 160) + 1,
        'rate_limit': {
            'limit': 50,
            'window': '1 hour',
            'remaining': 50 - await db.messages.count_documents({
                'tenant_id': current_user.tenant_id,
                'channel': 'sms',
                'sent_at': {'$gte': (datetime.now(UTC) - timedelta(hours=1)).isoformat()}
            })
        }
    }

    if message_warning:
        response['warning'] = message_warning

    return response

@router.post("/messages/send-whatsapp")
async def send_whatsapp(
    recipient: str,
    body: str,
    guest_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Send WhatsApp message with rate limiting (80 per hour)"""
    # WhatsApp rate limit
    if not await check_rate_limit(current_user.tenant_id, 'whatsapp', limit_per_hour=80):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 80 WhatsApp messages per hour. Please try again later."
        )

    # Validate phone number format
    if not recipient or not recipient.startswith('+'):
        raise HTTPException(status_code=400, detail="Invalid phone number format. Must start with + and country code")

    # Validate message body
    if not body or len(body.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    message = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'channel': 'whatsapp',
        'recipient': recipient,
        'body': body,
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id,
        'status': 'sent',
        'character_count': len(body)
    }

    await db.messages.insert_one(message)

    return {
        'message': 'WhatsApp sent successfully',
        'message_id': message['id'],
        'recipient': recipient,
        'character_count': len(body),
        'rate_limit': {
            'limit': 80,
            'window': '1 hour',
            'remaining': 80 - await db.messages.count_documents({
                'tenant_id': current_user.tenant_id,
                'channel': 'whatsapp',
                'sent_at': {'$gte': (datetime.now(UTC) - timedelta(hours=1)).isoformat()}
            })
        }
    }

@router.get("/messages/templates")
async def get_message_templates(
    channel: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get message templates"""
    query = {'tenant_id': current_user.tenant_id, 'active': True}
    if channel:
        query['channel'] = channel

    templates = await db.message_templates.find(query, {'_id': 0}).to_list(100)
    return {'templates': templates, 'count': len(templates)}

@router.post("/rms/generate-suggestions")
async def generate_rms_suggestions(
    start_date: str,
    end_date: str,
    room_type: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Generate RMS rate suggestions based on occupancy and demand"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    # Get all rooms or specific room type
    room_query = {'tenant_id': current_user.tenant_id}
    if room_type:
        room_query['room_type'] = room_type

    rooms = await db.rooms.find(room_query, {'_id': 0}).to_list(1000)
    room_types = list({r['room_type'] for r in rooms})

    suggestions = []

    for rt in room_types:
        rt_rooms = [r for r in rooms if r['room_type'] == rt]
        total_rooms = len(rt_rooms)

        # For each date in range
        current_date = start
        while current_date <= end:
            date_str = current_date.isoformat()

            # Calculate occupancy for this date
            start_of_day = datetime.combine(current_date, datetime.min.time())
            end_of_day = datetime.combine(current_date, datetime.max.time())

            bookings = await db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'room_id': {'$in': [r['id'] for r in rt_rooms]},
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$lte': end_of_day.isoformat()},
                'check_out': {'$gte': start_of_day.isoformat()}
            })

            occupancy_rate = (bookings / total_rooms * 100) if total_rooms > 0 else 0

            # Get current rate (or use base rate)
            base_rate = rt_rooms[0].get('base_price', 100)

            # Simple dynamic pricing logic
            if occupancy_rate >= 90:
                suggested_rate = base_rate * 1.3  # +30%
                reason = "Very high demand (90%+ occupancy)"
                confidence = 95
            elif occupancy_rate >= 75:
                suggested_rate = base_rate * 1.2  # +20%
                reason = "High demand (75%+ occupancy)"
                confidence = 85
            elif occupancy_rate >= 60:
                suggested_rate = base_rate * 1.1  # +10%
                reason = "Good demand (60%+ occupancy)"
                confidence = 75
            elif occupancy_rate <= 30:
                suggested_rate = base_rate * 0.85  # -15%
                reason = "Low demand (< 30% occupancy)"
                confidence = 80
            else:
                suggested_rate = base_rate
                reason = "Normal demand (30-60% occupancy)"
                confidence = 60

            # Create suggestion
            suggestion = RMSSuggestion(
                tenant_id=current_user.tenant_id,
                date=date_str,
                room_type=rt,
                current_rate=base_rate,
                suggested_rate=round(suggested_rate, 2),
                reason=reason,
                confidence_score=confidence,
                based_on={
                    'occupancy_rate': round(occupancy_rate, 2),
                    'bookings': bookings,
                    'total_rooms': total_rooms
                }
            )

            sugg_dict = suggestion.model_dump()
            sugg_dict['created_at'] = sugg_dict['created_at'].isoformat()
            await db.rms_suggestions.insert_one(sugg_dict)

            suggestions.append(suggestion)

            current_date += timedelta(days=1)

    return {
        'message': f'Generated {len(suggestions)} rate suggestions',
        'suggestions': suggestions[:20],  # Return first 20
        'total_count': len(suggestions)
    }

@router.get("/rms/suggestions")
async def get_rms_suggestions(
    status: str | None = None,
    date: str | None = None,
    room_type: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get RMS suggestions with filters"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    if date:
        query['date'] = date
    if room_type:
        query['room_type'] = room_type

    suggestions = await db.rms_suggestions.find(query, {'_id': 0}).sort('date', 1).to_list(100)
    return {'suggestions': suggestions, 'count': len(suggestions)}

@router.post("/rms/apply-suggestion/{suggestion_id}")
async def apply_rms_suggestion(
    suggestion_id: str,
    current_user: User = Depends(get_current_user)
):
    """Apply RMS suggestion to room rates"""
    suggestion = await db.rms_suggestions.find_one({
        'id': suggestion_id,
        'tenant_id': current_user.tenant_id
    })

    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if suggestion['status'] == 'applied':
        raise HTTPException(status_code=400, detail="Suggestion already applied")

    # Update rooms of this type with new rate
    await db.rooms.update_many(
        {
            'tenant_id': current_user.tenant_id,
            'room_type': suggestion['room_type']
        },
        {'$set': {'base_price': suggestion['suggested_rate']}}
    )

    # Mark suggestion as applied
    await db.rms_suggestions.update_one(
        {'id': suggestion_id},
        {'$set': {'status': 'applied'}}
    )

    # Audit log
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="APPLY_RMS_SUGGESTION",
        entity_type="rms_suggestion",
        entity_id=suggestion_id,
        changes={'old_rate': suggestion['current_rate'], 'new_rate': suggestion['suggested_rate'], 'room_type': suggestion['room_type']}
    )

    return {
        'message': f"Applied rate suggestion: {suggestion['room_type']} → ${suggestion['suggested_rate']}",
        'room_type': suggestion['room_type'],
        'new_rate': suggestion['suggested_rate']
    }

# Router will be included at the very end after ALL endpoints are defined

logger = logging.getLogger(__name__)

@router.get("/crm/reviews")
async def get_reviews(
    current_user: User = Depends(get_current_user)
):
    """Get guest reviews"""
    reviews = await db.guest_reviews.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('created_at', -1).to_list(1000)
    return {"reviews": reviews}

@router.post("/crm/reviews/{review_id}/respond")
async def respond_to_review(
    review_id: str,
    response_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Respond to a guest review"""
    await db.guest_reviews.update_one(
        {'id': review_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'response': response_data.get('response'),
            'responded_at': datetime.now(UTC).isoformat(),
            'responded_by': current_user.id
        }}
    )
    return {"message": "Response sent successfully"}

# ========================================

# 1. EXTERNAL REVIEW API INTEGRATION (Booking.com, Google, TripAdvisor)
@router.post("/feedback/external-review-webhook")
async def receive_external_review(
    request: ExternalReviewWebhookRequest,
    current_user: User = Depends(get_current_user)
):
    """Webhook to receive reviews from external platforms"""
    review = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'platform': request.platform,
        'external_review_id': request.review_id,
        'rating': request.rating,
        'reviewer_name': request.reviewer_name,
        'review_text': request.review_text,
        'review_date': request.review_date,
        'booking_reference': request.booking_reference,
        'status': 'new',
        'sentiment': 'positive' if request.rating >= 4.0 else ('neutral' if request.rating >= 3.0 else 'negative'),
        'received_at': datetime.now(UTC).isoformat()
    }

    review_copy = review.copy()
    await db.external_reviews.insert_one(review_copy)

    return {'message': 'External review received successfully', 'review_id': review['id']}

@router.get("/feedback/external-reviews")
async def get_external_reviews(
    platform: str = None,
    sentiment: str = None,
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get reviews from external platforms"""
    query = {'tenant_id': current_user.tenant_id}

    if platform:
        query['platform'] = platform
    if sentiment:
        query['sentiment'] = sentiment
    if start_date and end_date:
        query['review_date'] = {'$gte': start_date, '$lte': end_date}

    reviews = await db.external_reviews.find(
        query,
        {'_id': 0}
    ).sort('review_date', -1).to_list(1000)

    return {'reviews': reviews, 'count': len(reviews)}

@router.get("/feedback/external-reviews/summary")
async def get_external_reviews_summary(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get aggregated summary of external reviews"""
    query = {'tenant_id': current_user.tenant_id}

    if start_date and end_date:
        query['review_date'] = {'$gte': start_date, '$lte': end_date}

    reviews = await db.external_reviews.find(query, {'_id': 0}).to_list(10000)

    if not reviews:
        return {
            'message': 'No external reviews found',
            'summary': {}
        }

    # Calculate platform breakdown
    platform_stats = {}
    for review in reviews:
        platform = review.get('platform', 'unknown')
        if platform not in platform_stats:
            platform_stats[platform] = {
                'count': 0,
                'total_rating': 0,
                'positive': 0,
                'neutral': 0,
                'negative': 0
            }

        platform_stats[platform]['count'] += 1
        platform_stats[platform]['total_rating'] += review.get('rating', 0)

        sentiment = review.get('sentiment', 'neutral')
        platform_stats[platform][sentiment] += 1

    # Calculate averages
    for platform, stats in platform_stats.items():
        if stats['count'] > 0:
            stats['avg_rating'] = round(stats['total_rating'] / stats['count'], 2)

    # Overall stats
    total_reviews = len(reviews)
    avg_rating = sum(r.get('rating', 0) for r in reviews) / total_reviews if total_reviews > 0 else 0

    sentiment_breakdown = {
        'positive': sum(1 for r in reviews if r.get('sentiment') == 'positive'),
        'neutral': sum(1 for r in reviews if r.get('sentiment') == 'neutral'),
        'negative': sum(1 for r in reviews if r.get('sentiment') == 'negative')
    }

    return {
        'summary': {
            'total_reviews': total_reviews,
            'avg_rating': round(avg_rating, 2),
            'sentiment_breakdown': sentiment_breakdown,
            'platforms': platform_stats
        },
        'date_range': f"{start_date or 'all'} to {end_date or 'all'}"
    }

@router.post("/feedback/external-reviews/{review_id}/respond")
async def respond_to_external_review(
    review_id: str,
    response_text: str,
    current_user: User = Depends(get_current_user)
):
    """Respond to external review"""
    review = await db.external_reviews.find_one({
        'id': review_id,
        'tenant_id': current_user.tenant_id
    })

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    await db.external_reviews.update_one(
        {'id': review_id},
        {
            '$set': {
                'response': response_text,
                'responded_at': datetime.now(UTC).isoformat(),
                'responded_by': current_user.id,
                'status': 'responded'
            }
        }
    )

    return {'message': 'Response posted successfully'}


# 2. IN-HOUSE SURVEY SYSTEM
@router.get("/feedback/surveys")
async def get_surveys(current_user: User = Depends(get_current_user)):
    """Get all surveys"""
    surveys = await db.surveys.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)

    # Get response counts
    for survey in surveys:
        response_count = await db.survey_responses.count_documents({
            'tenant_id': current_user.tenant_id,
            'survey_id': survey['id']
        })
        survey['response_count'] = response_count

    return {'surveys': surveys, 'count': len(surveys)}

@router.post("/feedback/surveys")
async def create_survey(
    request: CreateSurveyRequest,
    current_user: User = Depends(get_current_user)
):
    """Create new survey"""
    survey = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'survey_name': request.survey_name,
        'description': request.description,
        'target_department': request.target_department,
        'questions': request.questions,
        'trigger': request.trigger,
        'status': 'active',
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
    }

    survey_copy = survey.copy()
    await db.surveys.insert_one(survey_copy)
    return survey

@router.post("/feedback/surveys/response")
async def submit_survey_response(
    request: SubmitSurveyResponseRequest,
    current_user: User = Depends(get_current_user)
):
    """Submit survey response"""
    # Verify survey exists
    survey = await db.surveys.find_one({
        'id': request.survey_id,
        'tenant_id': current_user.tenant_id
    })

    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    # Calculate overall rating
    ratings = [r.get('rating') for r in request.responses if r.get('rating')]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    response = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'survey_id': request.survey_id,
        'survey_name': survey.get('survey_name'),
        'booking_id': request.booking_id,
        'guest_name': request.guest_name,
        'guest_email': request.guest_email,
        'responses': request.responses,
        'overall_rating': round(avg_rating, 2) if avg_rating else None,
        'submitted_at': datetime.now(UTC).isoformat()
    }

    response_copy = response.copy()
    await db.survey_responses.insert_one(response_copy)

    return {'message': 'Survey response submitted successfully', 'response_id': response['id']}

@router.get("/feedback/surveys/{survey_id}/responses")
async def get_survey_responses(
    survey_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get responses for specific survey"""
    # Verify survey
    survey = await db.surveys.find_one({
        'id': survey_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    # Get responses
    responses = await db.survey_responses.find({
        'tenant_id': current_user.tenant_id,
        'survey_id': survey_id
    }, {'_id': 0}).to_list(1000)

    # Calculate statistics
    if responses:
        ratings = [r.get('overall_rating') for r in responses if r.get('overall_rating')]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0

        # Aggregate answers per question
        question_stats = {}
        for response in responses:
            for answer in response.get('responses', []):
                q_id = answer.get('question_id', 'unknown')
                if q_id not in question_stats:
                    question_stats[q_id] = {
                        'ratings': [],
                        'answers': []
                    }

                if answer.get('rating'):
                    question_stats[q_id]['ratings'].append(answer['rating'])
                if answer.get('answer'):
                    question_stats[q_id]['answers'].append(answer['answer'])

        # Calculate averages
        for q_id, stats in question_stats.items():
            if stats['ratings']:
                stats['avg_rating'] = round(sum(stats['ratings']) / len(stats['ratings']), 2)
    else:
        avg_rating = 0
        question_stats = {}

    return {
        'survey': survey,
        'responses': responses,
        'statistics': {
            'total_responses': len(responses),
            'avg_overall_rating': round(avg_rating, 2),
            'question_stats': question_stats
        }
    }


# 3. DEPARTMENT-BASED SATISFACTION TRACKING
@router.post("/feedback/department")
async def submit_department_feedback(
    request: CreateDepartmentFeedbackRequest,
    current_user: User = Depends(get_current_user)
):
    """Submit feedback for specific department"""
    feedback = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'department': request.department,
        'booking_id': request.booking_id,
        'guest_name': request.guest_name,
        'rating': request.rating,
        'comment': request.comment,
        'staff_member': request.staff_member,
        'sentiment': 'positive' if request.rating >= 4 else ('neutral' if request.rating == 3 else 'negative'),
        'submitted_at': datetime.now(UTC).isoformat()
    }

    feedback_copy = feedback.copy()
    await db.department_feedback.insert_one(feedback_copy)

    return {'message': 'Department feedback submitted successfully', 'feedback_id': feedback['id']}

@router.get("/feedback/department")
async def get_department_feedback(
    department: str = None,
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get department feedback"""
    query = {'tenant_id': current_user.tenant_id}

    if department:
        query['department'] = department

    if start_date and end_date:
        query['submitted_at'] = {'$gte': start_date, '$lte': end_date}

    feedback = await db.department_feedback.find(
        query,
        {'_id': 0}
    ).sort('submitted_at', -1).to_list(1000)

    return {'feedback': feedback, 'count': len(feedback)}

@router.get("/feedback/department/summary")
async def get_department_satisfaction_summary(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get department satisfaction summary"""
    query = {'tenant_id': current_user.tenant_id}

    if start_date and end_date:
        query['submitted_at'] = {'$gte': start_date, '$lte': end_date}

    feedback = await db.department_feedback.find(query, {'_id': 0}).to_list(10000)

    if not feedback:
        return {
            'message': 'No department feedback found',
            'summary': {}
        }

    # Aggregate by department
    dept_stats = {}
    departments = ['housekeeping', 'front_desk', 'fnb', 'spa', 'concierge']

    for dept in departments:
        dept_feedback = [f for f in feedback if f.get('department') == dept]

        if dept_feedback:
            ratings = [f.get('rating', 0) for f in dept_feedback]
            avg_rating = sum(ratings) / len(ratings) if ratings else 0

            sentiment_counts = {
                'positive': sum(1 for f in dept_feedback if f.get('sentiment') == 'positive'),
                'neutral': sum(1 for f in dept_feedback if f.get('sentiment') == 'neutral'),
                'negative': sum(1 for f in dept_feedback if f.get('sentiment') == 'negative')
            }

            dept_stats[dept] = {
                'total_feedback': len(dept_feedback),
                'avg_rating': round(avg_rating, 2),
                'sentiment_breakdown': sentiment_counts,
                'satisfaction_rate': round((sentiment_counts['positive'] / len(dept_feedback) * 100), 1) if dept_feedback else 0
            }
        else:
            dept_stats[dept] = {
                'total_feedback': 0,
                'avg_rating': 0,
                'sentiment_breakdown': {'positive': 0, 'neutral': 0, 'negative': 0},
                'satisfaction_rate': 0
            }

    # Overall stats
    all_ratings = [f.get('rating', 0) for f in feedback]
    overall_avg = sum(all_ratings) / len(all_ratings) if all_ratings else 0

    # Staff member performance
    staff_performance = {}
    for f in feedback:
        if f.get('staff_member'):
            staff = f['staff_member']
            if staff not in staff_performance:
                staff_performance[staff] = {
                    'ratings': [],
                    'department': f.get('department')
                }
            staff_performance[staff]['ratings'].append(f.get('rating', 0))

    # Calculate staff averages
    staff_stats = []
    for staff, data in staff_performance.items():
        if data['ratings']:
            avg = sum(data['ratings']) / len(data['ratings'])
            staff_stats.append({
                'staff_member': staff,
                'department': data['department'],
                'avg_rating': round(avg, 2),
                'feedback_count': len(data['ratings'])
            })

    staff_stats.sort(key=lambda x: x['avg_rating'], reverse=True)

    return {
        'summary': {
            'total_feedback': len(feedback),
            'overall_avg_rating': round(overall_avg, 2),
            'departments': dept_stats,
            'top_performers': staff_stats[:10],
            'needs_attention': [
                {'department': dept, 'avg_rating': stats['avg_rating']}
                for dept, stats in dept_stats.items()
                if stats['avg_rating'] > 0 and stats['avg_rating'] < 3.5
            ]
        },
        'date_range': f"{start_date or 'all'} to {end_date or 'all'}"
    }


# ============= GUEST MOBILE APP ENDPOINTS =============

@router.get("/guest/bookings")
@cached(ttl=300, key_prefix="guest_bookings_history")  # Cache for 5 min
async def get_guest_bookings(
    current_user: User = Depends(get_current_user)
):
    """Get guest's bookings across ALL hotels (multi-tenant support)"""
    # Find ALL guest records across all tenants with this email
    guest_records = []
    async for guest in db.guests.find({'email': current_user.email}):
        guest_records.append(guest)

    guest_ids = [g['id'] for g in guest_records]

    if not guest_ids:
        # No guest records found, return empty
        return {'active_bookings': [], 'past_bookings': []}

    # Get ALL bookings across all tenants for these guest IDs
    all_bookings = []
    async for booking in db.bookings.find({'guest_id': {'$in': guest_ids}}).sort('check_in', -1):
        # Get room details
        room = await db.rooms.find_one({'id': booking.get('room_id')})

        # Get guest details
        guest = await db.guests.find_one({'id': booking.get('guest_id')})

        # Get tenant/hotel details for THIS booking
        tenant = await db.tenants.find_one({'id': booking.get('tenant_id')})

        # Helper to make datetime timezone-aware
        def make_aware(dt_str):
            if not dt_str:
                return None
            try:
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except Exception:
                return None

        check_in_dt = make_aware(booking.get('check_in'))
        now_utc = datetime.now(UTC)

        booking_data = {
            'id': booking.get('id'),
            'tenant_id': booking.get('tenant_id'),
            'confirmation_number': booking.get('confirmation_number', booking.get('id')[:8].upper()),
            'check_in': booking.get('check_in'),
            'check_out': booking.get('check_out'),
            'status': booking.get('status'),
            'guests_count': booking.get('adults', 1) + booking.get('children', 0),
            'total_amount': booking.get('total_amount', 0),
            'guest_name': guest.get('name') if guest else current_user.name,
            'qr_code_data': booking.get('qr_code_data'),
            'can_checkin': booking.get('status') == 'confirmed' and check_in_dt and check_in_dt <= now_utc,
            'can_communicate': booking.get('status') in ['confirmed', 'checked_in'],
            'can_order_services': booking.get('status') == 'checked_in',
            # Nested hotel data for frontend
            'hotel': {
                'id': tenant.get('id') if tenant else None,
                'property_name': tenant.get('property_name', 'Hotel') if tenant else 'Hotel',
                'hotel_name': tenant.get('hotel_name', tenant.get('property_name', 'Hotel')) if tenant else 'Hotel',
                'address': tenant.get('address', 'City Center') if tenant else 'City Center'
            },
            # Nested room data for frontend
            'room': {
                'room_number': room.get('room_number', 'TBA') if room else 'TBA',
                'room_type': room.get('room_type', 'Standard') if room else 'Standard',
                'floor': room.get('floor', 1) if room else 1
            }
        }

        all_bookings.append(booking_data)

    # Separate active and past
    now = datetime.now(UTC)
    active_bookings = []
    past_bookings = []

    for b in all_bookings:
        try:
            # Parse checkout date and make it timezone aware if needed
            checkout_dt = datetime.fromisoformat(b['check_out'])
            if checkout_dt.tzinfo is None:
                checkout_dt = checkout_dt.replace(tzinfo=UTC)

            # Categorize booking
            if b['status'] in ['confirmed', 'checked_in', 'guaranteed'] and checkout_dt >= now:
                active_bookings.append(b)
            elif b['status'] == 'checked_out' or (checkout_dt < now and b['status'] not in ['checked_in', 'confirmed', 'guaranteed']):
                past_bookings.append(b)
        except Exception:
            # If date parsing fails, default to past booking
            if b['status'] == 'checked_out':
                past_bookings.append(b)
            else:
                active_bookings.append(b)

    return {
        'active_bookings': active_bookings,
        'past_bookings': past_bookings[:10]  # Last 10
    }


@router.get("/guest/loyalty")
async def get_guest_loyalty(
    current_user: User = Depends(get_current_user)
):
    """Get guest loyalty information across ALL hotels (multi-tenant support)"""
    # Find ALL guest records across all tenants with this email
    guest_records = []
    async for guest in db.guests.find({'email': current_user.email}):
        guest_records.append(guest)

    if not guest_records:
        return {
            'total_points': 0,
            'loyalty_programs': [],
            'upcoming_rewards': [],
            'global_tier': 'bronze'
        }

    # Build loyalty programs array - one per hotel
    loyalty_programs = []
    total_points_all_hotels = 0

    for guest in guest_records:
        tenant = await db.tenants.find_one({'id': guest.get('tenant_id')})
        loyalty_points = guest.get('loyalty_points', 0)
        loyalty_tier = guest.get('loyalty_tier', 'bronze')
        total_points_all_hotels += loyalty_points

        # Get loyalty program benefits for this hotel
        benefits = await db.loyalty_benefits.find_one({
            'tenant_id': guest.get('tenant_id'),
            'tier': loyalty_tier
        })

        # Calculate points to next tier

        next_tier = None
        points_to_next = 0

        if loyalty_tier == 'bronze':
            next_tier = 'silver'
            points_to_next = 1000 - loyalty_points
        elif loyalty_tier == 'silver':
            next_tier = 'gold'
            points_to_next = 5000 - loyalty_points
        elif loyalty_tier == 'gold':
            next_tier = 'platinum'
            points_to_next = 10000 - loyalty_points

        # Get recent point transactions for this hotel
        transactions = []
        async for txn in db.loyalty_transactions.find({
            'tenant_id': guest.get('tenant_id'),
            'guest_id': guest.get('id')
        }).sort('created_at', -1).limit(5):
            transactions.append(txn)

        loyalty_programs.append({
            'id': guest.get('id'),
            'hotel_id': guest.get('tenant_id'),
            'hotel_name': tenant.get('property_name', 'Hotel') if tenant else 'Hotel',
            'tier': loyalty_tier,
            'points': loyalty_points,
            'next_tier': next_tier,
            'points_to_next_tier': max(0, points_to_next) if next_tier else 0,
            'tier_benefits': benefits.get('benefits', []) if benefits else [],
            'recent_transactions': transactions
        })

    # Calculate global tier based on total points across all hotels
    if total_points_all_hotels >= 10000:
        global_tier = 'platinum'
    elif total_points_all_hotels >= 5000:
        global_tier = 'gold'
    elif total_points_all_hotels >= 1000:
        global_tier = 'silver'
    else:
        global_tier = 'bronze'

    return {
        'total_points': total_points_all_hotels,
        'global_tier': global_tier,
        'loyalty_programs': loyalty_programs,
        'upcoming_rewards': [
            {
                'name': 'Free Night Stay',
                'points_required': 5000,
                'points_remaining': max(0, 5000 - total_points_all_hotels)
            },
            {
                'name': 'Room Upgrade',
                'points_required': 2000,
                'points_remaining': max(0, 2000 - total_points_all_hotels)
            },
            {
                'name': 'Late Checkout',
                'points_required': 500,
                'points_remaining': max(0, 500 - total_points_all_hotels)
            }
        ]
    }


@router.get("/guest/notification-preferences")
async def get_notification_preferences(
    current_user: User = Depends(get_current_user)
):
    """Get guest notification preferences (user-level, not tenant-specific)"""
    prefs = await db.guest_notification_preferences.find_one(
        {'user_id': current_user.id},
        {'_id': 0}  # Exclude MongoDB ObjectId
    )

    if not prefs:
        # Default preferences
        return {
            'user_id': current_user.id,
            'email_notifications': True,
            'sms_notifications': False,
            'push_notifications': True,
            'whatsapp_notifications': False,
            'booking_confirmations': True,
            'check_in_reminders': True,
            'promotional_offers': True,
            'loyalty_updates': True
        }

    return prefs


@router.put("/guest/notification-preferences")
async def update_notification_preferences(
    preferences: dict,
    current_user: User = Depends(get_current_user)
):
    """Update guest notification preferences (user-level, applies to all hotels)"""
    # Add user_id to the update
    update_data = {**preferences, 'user_id': current_user.id}

    await db.guest_notification_preferences.update_one(
        {'user_id': current_user.id},
        {'$set': update_data},
        upsert=True
    )

    return {'message': 'Preferences updated successfully', 'preferences': update_data}


@router.post("/guest/device-token")
async def register_device_token(
    device_token: str,
    platform: str,  # ios, android, web
    current_user: User = Depends(get_current_user)
):
    """Register device token for push notifications"""
    await db.guest_device_tokens.update_one(
        {
            'tenant_id': current_user.tenant_id,
            'user_id': current_user.id,
            'device_token': device_token
        },
        {
            '$set': {
                'tenant_id': current_user.tenant_id,
                'user_id': current_user.id,
                'device_token': device_token,
                'platform': platform,
                'updated_at': datetime.now(UTC).isoformat()
            }
        },
        upsert=True
    )

    return {
        'success': True,
        'message': 'Device token registered'
    }


@router.get("/guest/room-service-menu")
async def get_room_service_menu(
    current_user: User = Depends(get_current_user)
):
    """Get room service menu"""
    menu_items = []
    async for item in db.room_service_menu.find({
        'tenant_id': current_user.tenant_id,
        'available': True
    }).sort('category', 1):
        menu_items.append(item)

    # If no menu exists, return sample menu
    if not menu_items:
        return {
            'categories': [
                {
                    'name': 'Breakfast',
                    'items': [
                        {'id': '1', 'name': 'Continental Breakfast', 'price': 15.00, 'description': 'Croissant, juice, coffee'},
                        {'id': '2', 'name': 'American Breakfast', 'price': 18.00, 'description': 'Eggs, bacon, toast, coffee'}
                    ]
                },
                {
                    'name': 'Lunch & Dinner',
                    'items': [
                        {'id': '3', 'name': 'Club Sandwich', 'price': 14.00, 'description': 'Triple decker with fries'},
                        {'id': '4', 'name': 'Caesar Salad', 'price': 12.00, 'description': 'With grilled chicken'}
                    ]
                },
                {
                    'name': 'Beverages',
                    'items': [
                        {'id': '5', 'name': 'Fresh Juice', 'price': 6.00, 'description': 'Orange or apple'},
                        {'id': '6', 'name': 'Soft Drinks', 'price': 4.00, 'description': 'Coca Cola, Sprite, Fanta'}
                    ]
                }
            ]
        }

    # Group by category
    categories = {}
    for item in menu_items:
        cat = item.get('category', 'Other')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    return {
        'categories': [
            {'name': cat, 'items': items}
            for cat, items in categories.items()
        ]
    }


@router.post("/guest/room-service-order")
async def create_room_service_order(
    booking_id: str,
    items: list[dict],
    special_instructions: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Create room service order"""
    # Verify booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found")

    # Calculate total
    total_amount = sum(item.get('price', 0) * item.get('quantity', 1) for item in items)

    order = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'room_id': booking.get('room_id'),
        'guest_id': current_user.id,
        'items': items,
        'total_amount': total_amount,
        'special_instructions': special_instructions,
        'status': 'pending',  # pending, confirmed, preparing, delivered, cancelled
        'ordered_at': datetime.now(UTC).isoformat(),
        'estimated_delivery': (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    }

    await db.room_service_orders.insert_one(order)

    # Post charge to folio
    folio = await db.folios.find_one({
        'booking_id': booking_id,
        'folio_type': 'guest',
        'status': 'open'
    })

    if folio:
        charge = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'folio_id': folio['id'],
            'booking_id': booking_id,
            'date': datetime.now(UTC).date().isoformat(),
            'charge_category': 'food',
            'description': 'Room Service',
            'unit_price': total_amount,
            'quantity': 1,
            'amount': total_amount,
            'tax_rate': 0.18,
            'tax_amount': round(total_amount * 0.18, 2),
            'total': round(total_amount * 1.18, 2),
            'posted_by': 'Guest App'
        }

        await db.folio_charges.insert_one(charge)

    return {
        'success': True,
        'order_id': order['id'],
        'estimated_delivery': order['estimated_delivery'],
        'total_amount': total_amount
    }


@router.get("/guest/room-service-orders/{booking_id}")
async def get_room_service_orders(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get room service orders for a booking"""
    orders = []
    async for order in db.room_service_orders.find({
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id
    }).sort('ordered_at', -1):
        orders.append(order)

    return {'orders': orders}


@router.post("/guest/request")
async def create_guest_request(
    booking_id: str,
    request_type: str,  # housekeeping, maintenance, concierge, other
    description: str,
    priority: str = 'normal',  # low, normal, high, urgent
    current_user: User = Depends(get_current_user)
):
    """Create guest request"""
    # Verify booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found")

    request = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'room_id': booking.get('room_id'),
        'guest_id': current_user.id,
        'request_type': request_type,
        'description': description,
        'priority': priority,
        'status': 'pending',  # pending, in_progress, completed, cancelled
        'created_at': datetime.now(UTC).isoformat(),
        'resolved_at': None
    }

    await db.guest_requests.insert_one(request)

    # Create task for appropriate department
    department_map = {
        'housekeeping': 'housekeeping',
        'maintenance': 'engineering',
        'concierge': 'concierge',
        'other': 'front_desk'
    }

    task = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'title': f'Guest Request: {request_type}',
        'description': description,
        'department': department_map.get(request_type, 'front_desk'),
        'priority': priority,
        'status': 'pending',
        'room_id': booking.get('room_id'),
        'related_request_id': request['id'],
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.staff_tasks.insert_one(task)

    return {
        'success': True,
        'request_id': request['id'],
        'message': 'Request submitted successfully'
    }


@router.get("/guest/requests/{booking_id}")
async def get_guest_requests(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get guest requests for a booking"""
    requests = []
    async for req in db.guest_requests.find({
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id
    }).sort('created_at', -1):
        requests.append(req)

    return {'requests': requests}


@router.get("/guest/profile")
async def get_guest_profile(
    current_user: User = Depends(get_current_user)
):
    """Get guest profile"""
    guest = await db.guests.find_one({
        'email': current_user.email,
        'tenant_id': current_user.tenant_id
    })

    if not guest:
        return {
            'name': current_user.name,
            'email': current_user.email,
            'phone': '',
            'nationality': '',
            'preferences': {}
        }

    return {
        'id': guest.get('id'),
        'name': guest.get('name'),
        'email': guest.get('email'),
        'phone': guest.get('phone', ''),
        'nationality': guest.get('nationality', ''),
        'date_of_birth': guest.get('date_of_birth', ''),
        'preferences': guest.get('preferences', {}),
        'loyalty_tier': guest.get('loyalty_tier', 'bronze'),
        'loyalty_points': guest.get('loyalty_points', 0)
    }


@router.put("/guest/profile")
async def update_guest_profile(
    profile_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update guest profile"""
    guest = await db.guests.find_one({
        'email': current_user.email,
        'tenant_id': current_user.tenant_id
    })

    if not guest:
        # Create guest profile
        guest_id = str(uuid.uuid4())
        guest_data = {
            'id': guest_id,
            'tenant_id': current_user.tenant_id,
            'name': profile_data.get('name', current_user.name),
            'email': current_user.email,
            'phone': profile_data.get('phone', ''),
            'nationality': profile_data.get('nationality', ''),
            'date_of_birth': profile_data.get('date_of_birth', ''),
            'preferences': profile_data.get('preferences', {}),
            'created_at': datetime.now(UTC).isoformat()
        }
        await db.guests.insert_one(guest_data)
        return {'success': True, 'message': 'Profile created'}

    # Update existing profile
    update_data = {
        'name': profile_data.get('name', guest.get('name')),
        'phone': profile_data.get('phone', guest.get('phone')),
        'nationality': profile_data.get('nationality', guest.get('nationality')),
        'date_of_birth': profile_data.get('date_of_birth', guest.get('date_of_birth')),
        'preferences': profile_data.get('preferences', guest.get('preferences', {})),
        'updated_at': datetime.now(UTC).isoformat()
    }

    await db.guests.update_one(
        {'id': guest['id']},
        {'$set': update_data}
    )

    return {'success': True, 'message': 'Profile updated'}


@router.post("/guest/web-checkin/{booking_id}")
async def web_checkin(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Perform web check-in"""
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'confirmed'
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or already checked in")

    # Check if check-in date is today or past
    check_in_date = datetime.fromisoformat(booking['check_in'])
    if check_in_date.date() > datetime.now(UTC).date():
        raise HTTPException(status_code=400, detail="Cannot check in before check-in date")

    # Update booking status to web_checked_in
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'status': 'web_checked_in',
            'web_checkin_at': datetime.now(UTC).isoformat()
        }}
    )

    # Generate digital key QR code
    digital_key = {
        'booking_id': booking_id,
        'room_id': booking.get('room_id'),
        'valid_from': datetime.now(UTC).isoformat(),
        'valid_until': booking['check_out'],
        'key_code': str(uuid.uuid4())[:8].upper()
    }

    return {
        'success': True,
        'message': 'Web check-in completed',
        'digital_key': digital_key,
        'qr_code_data': booking.get('qr_code_data'),
        'room_ready': True,  # TODO: Check actual room status
        'instructions': 'Show this QR code at the front desk or use it with smart lock'
    }


@router.get("/logs/alerts-history")
async def get_alert_history(
    start_date: str | None = None,
    end_date: str | None = None,
    alert_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    source_module: str | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get alert center history
    - Filter by date, type, severity, status
    - Includes response time metrics
    """
    query = {'tenant_id': current_user.tenant_id}

    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            date_filter['$lte'] = end_date
        if date_filter:
            query['timestamp'] = date_filter

    if alert_type:
        query['alert_type'] = alert_type
    if severity:
        query['severity'] = severity
    if status:
        query['status'] = status
    if source_module:
        query['source_module'] = source_module

    alerts = []
    async for alert in db.alert_history.find(query).sort('timestamp', -1).skip(skip).limit(limit):
        alerts.append(alert)

    total_count = await db.alert_history.count_documents(query)

    # Calculate stats
    stats = {
        'total_alerts': total_count,
        'unread': 0,
        'acknowledged': 0,
        'resolved': 0,
        'by_severity': {},
        'by_module': {}
    }

    async for alert in db.alert_history.find({'tenant_id': current_user.tenant_id}):
        status = alert.get('status', 'unread')
        if status == 'unread':
            stats['unread'] += 1
        elif status == 'acknowledged':
            stats['acknowledged'] += 1
        elif status == 'resolved':
            stats['resolved'] += 1

        # Count by severity
        severity = alert.get('severity', 'medium')
        stats['by_severity'][severity] = stats['by_severity'].get(severity, 0) + 1

        # Count by module
        module = alert.get('source_module', 'system')
        stats['by_module'][module] = stats['by_module'].get(module, 0) + 1

    return {
        'alerts': alerts,
        'total_count': total_count,
        'returned_count': len(alerts),
        'skip': skip,
        'limit': limit,
        'stats': stats
    }


@router.post("/logs/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user)
):
    """Acknowledge an alert"""
    result = await db.alerts.update_one(
        {
            'id': alert_id,
            'tenant_id': current_user.tenant_id
        },
        {
            '$set': {
                'status': 'acknowledged',
                'acknowledged_at': datetime.now(UTC).isoformat(),
                'acknowledged_by': current_user.id
            }
        }
    )

    # Also update history
    await db.alert_history.update_one(
        {'id': alert_id},
        {
            '$set': {
                'status': 'acknowledged',
                'acknowledged_at': datetime.now(UTC).isoformat(),
                'acknowledged_by': current_user.id
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        'success': True,
        'message': 'Alert acknowledged'
    }


@router.post("/logs/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolution_notes: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Resolve an alert"""
    result = await db.alerts.update_one(
        {
            'id': alert_id,
            'tenant_id': current_user.tenant_id
        },
        {
            '$set': {
                'status': 'resolved',
                'resolved_at': datetime.now(UTC).isoformat(),
                'resolved_by': current_user.id,
                'resolution_notes': resolution_notes
            }
        }
    )

    # Also update history
    await db.alert_history.update_one(
        {'id': alert_id},
        {
            '$set': {
                'status': 'resolved',
                'resolved_at': datetime.now(UTC).isoformat(),
                'resolved_by': current_user.id,
                'resolution_notes': resolution_notes
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        'success': True,
        'message': 'Alert resolved'
    }


@router.get("/logs/dashboard")
async def get_logs_dashboard(
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive logging dashboard
    - Overview of all log types
    - Recent errors, alerts
    - System health indicators
    """
    # Get counts for each log type
    error_count = await db.error_logs.count_documents({'tenant_id': current_user.tenant_id})
    night_audit_count = await db.night_audit_logs.count_documents({'tenant_id': current_user.tenant_id})
    ota_sync_count = await db.ota_sync_logs.count_documents({'tenant_id': current_user.tenant_id})
    rms_publish_count = await db.rms_publish_logs.count_documents({'tenant_id': current_user.tenant_id})
    maintenance_prediction_count = await db.maintenance_prediction_logs.count_documents({'tenant_id': current_user.tenant_id})
    alert_count = await db.alert_history.count_documents({'tenant_id': current_user.tenant_id})

    # Recent critical errors (last 24 hours)
    from datetime import timedelta
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    recent_critical_errors = []
    async for error in db.error_logs.find({
        'tenant_id': current_user.tenant_id,
        'severity': 'critical',
        'timestamp': {'$gte': yesterday},
        'resolved': False
    }).sort('timestamp', -1).limit(5):
        recent_critical_errors.append(error)

    # Unread alerts
    unread_alerts = []
    async for alert in db.alerts.find({
        'tenant_id': current_user.tenant_id,
        'status': 'unread'
    }).sort('timestamp', -1).limit(10):
        unread_alerts.append(alert)

    # System health indicators
    health = {
        'overall_status': 'healthy',
        'indicators': []
    }

    # Check for critical errors
    if len(recent_critical_errors) > 0:
        health['overall_status'] = 'warning'
        health['indicators'].append({
            'type': 'critical_errors',
            'status': 'warning',
            'message': f'{len(recent_critical_errors)} critical errors in last 24 hours'
        })

    # Check for failed night audits
    failed_audits = await db.night_audit_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'failed',
        'timestamp': {'$gte': yesterday}
    })

    if failed_audits > 0:
        health['overall_status'] = 'warning'
        health['indicators'].append({
            'type': 'night_audit',
            'status': 'warning',
            'message': f'{failed_audits} failed night audits in last 24 hours'
        })

    # Check for OTA sync failures
    failed_syncs = await db.ota_sync_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'failed',
        'timestamp': {'$gte': yesterday}
    })

    if failed_syncs > 2:
        health['overall_status'] = 'warning'
        health['indicators'].append({
            'type': 'ota_sync',
            'status': 'warning',
            'message': f'{failed_syncs} failed OTA syncs in last 24 hours'
        })

    if len(health['indicators']) == 0:
        health['indicators'].append({
            'type': 'all_systems',
            'status': 'healthy',
            'message': 'All systems operating normally'
        })

    return {
        'summary': {
            'total_errors': error_count,
            'total_night_audits': night_audit_count,
            'total_ota_syncs': ota_sync_count,
            'total_rms_publishes': rms_publish_count,
            'total_maintenance_predictions': maintenance_prediction_count,
            'total_alerts': alert_count
        },
        'recent_critical_errors': recent_critical_errors,
        'unread_alerts': unread_alerts,
        'health': health
    }


