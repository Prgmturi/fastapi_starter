from structlog.typing import EventDict, Processor, WrappedLogger


def make_service_info_processor(
    app_name: str, version: str, environment: str
) -> Processor:
    """Factory: captures app metadata once at startup, returns a processor."""

    def add_service_info(
        logger: WrappedLogger,
        method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        event_dict["service"] = app_name
        event_dict["version"] = version
        event_dict["environment"] = environment
        return event_dict

    return add_service_info


def clean_event_dict(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    keys_to_remove = ["_record", "_from_structlog"]
    for key in keys_to_remove:
        event_dict.pop(key, None)

    return event_dict


def drop_color_message_key(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    event_dict.pop("color_message", None)
    return event_dict
