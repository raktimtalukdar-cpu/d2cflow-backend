from ..database import get_db
import logging

logger = logging.getLogger(__name__)


def log_event(event_type: str, entity_type: str = None, entity_id: str = None,
              status: str = "success", message: str = None, payload: dict = None):
    try:
        get_db().table("automation_logs").insert({
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "status": status,
            "message": message,
            "payload": payload,
        }).execute()
    except Exception as e:
        logger.error(f"Failed to write automation log: {e}")
