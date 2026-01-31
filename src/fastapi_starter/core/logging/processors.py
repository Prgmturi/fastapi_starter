from typing import Any

from fastapi_starter.core.config import get_settings


def add_service_info(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    event_dict["service"] = settings.app.name
    event_dict["version"] = settings.app.version
    event_dict["environment"] = settings.app.environment

    return event_dict


def clean_event_dict(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    keys_to_remove = ["_record", "_from_structlog"]
    for key in keys_to_remove:
        event_dict.pop(key, None)

    return event_dict


def drop_color_message_key(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    event_dict.pop("color_message", None)
    return event_dict
