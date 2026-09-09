from typing import Any

from pydantic import BaseModel


class MeetingResponse(BaseModel):
    date: str
    meetings: dict[str, Any]
