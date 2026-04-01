from app import db
from app.models import MailingListSubscriber


def upsert_subscriber(
    email,
    first_name=None,
    last_name=None,
    source=None,
    organization_id=None,
    notes=None,
    is_active=True,
):
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return None

    subscriber = MailingListSubscriber.query.filter_by(email=normalized_email).first()
    if subscriber:
        if first_name and not subscriber.first_name:
            subscriber.first_name = first_name[:100]
        if last_name and not subscriber.last_name:
            subscriber.last_name = last_name[:100]
        if organization_id and not subscriber.organization_id:
            subscriber.organization_id = organization_id
        if source and not subscriber.source:
            subscriber.source = source[:100]
        if notes and not subscriber.notes:
            subscriber.notes = notes
        if is_active:
            subscriber.is_active = True
        return subscriber

    subscriber = MailingListSubscriber(
        email=normalized_email,
        first_name=first_name[:100] if first_name else None,
        last_name=last_name[:100] if last_name else None,
        source=source[:100] if source else None,
        organization_id=organization_id,
        notes=notes,
        is_active=is_active,
    )
    db.session.add(subscriber)
    return subscriber
