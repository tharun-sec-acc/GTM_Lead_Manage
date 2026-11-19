import logging
from app.booking.services.reservation_service import ReservationService
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def cleanup_expired_booking_reservations_sync() -> int:
    with SessionLocal() as session:
        count = ReservationService.cleanup_expired(session)
        if count > 0:
            logger.info("Cleaned up %d expired booking reservations.", count)
        return count
