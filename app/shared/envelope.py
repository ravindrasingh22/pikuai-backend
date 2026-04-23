from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def envelope(data: Any, message: str | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "message": message,
        "data": data,
        "errors": [],
        "meta": {
            "request_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }
