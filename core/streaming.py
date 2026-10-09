from types import GeneratorType
import json


def normalize_stream_value(value):
    """Make an agent event JSON-serializable (dict/list/generator/bytes -> plain values)."""
    if isinstance(value, dict):
        return {str(k): normalize_stream_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize_stream_value(v) for v in value]
    if isinstance(value, GeneratorType):
        return [normalize_stream_value(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def serialize_stream_event(event):
    return json.dumps(normalize_stream_value(event), default=str)
