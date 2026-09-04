"""The response contract, enforced by the model rather than requested from it.

Structured Outputs constrains generation to this schema, so a malformed shape
such as prose followed by the control object is not improbable — it cannot be
generated. That is why nothing downstream carries a parse fallback.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

OrderType = Literal["pickup", "cake", "catering", "cake/catering", "delivery"]


class OrderItem(BaseModel):
    """One priced line. The application overwrites these with the tool result."""

    model_config = ConfigDict(extra="forbid")

    name: str
    quantity: int
    unit_price: float
    line_total: float


class Order(BaseModel):
    """The structured pickup order accompanying order_ready.

    service._build_ready_order replaces every item and money value with the
    actual price_order result, so what the model puts here is a statement of
    intent, not the source of truth. It is part of the contract because
    downstream integrations read the shape and because customer_name is used as
    a name fallback in service.py.
    """

    model_config = ConfigDict(extra="forbid")

    customer_name: str
    fulfillment: Literal["pickup"]
    items: list[OrderItem]
    subtotal: float
    tax: float
    total: float
    preparation_minutes: int


class CallResponse(BaseModel):
    """One assistant turn. Every field is required under strict mode."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    call_ended: bool
    order_ready: bool
    order: Optional[Order]
    order_type: Optional[OrderType]
    user_name: Optional[str]
    name: Optional[str]
    To_manager: bool
    Transfer_to_Manager: bool
    tools_called: bool
    summary: str
    verbatim_user_chat: list[str]
