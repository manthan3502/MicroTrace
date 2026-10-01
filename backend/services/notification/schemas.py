from pydantic import BaseModel, Field


class NotifyRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=100)
