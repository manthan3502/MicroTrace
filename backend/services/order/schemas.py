from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OrderRequest(BaseModel):
    item: str = Field(default="demo-item", min_length=1, max_length=100)
    scenario: Literal["normal", "slow_payment", "payment_error"] = "normal"
    slow_ms: int = 800

    @field_validator("slow_ms")
    @classmethod
    def validate_delay(cls, value, info):
        if info.data.get("scenario") != "slow_payment":
            return 800
        if not 100 <= value <= 3000:
            raise ValueError("slow_ms must be between 100 and 3000")
        return value
