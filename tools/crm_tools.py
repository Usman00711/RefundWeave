from langchain_core.tools import tool

from application.support_service import SupportService
from infrastructure.database import get_database_url

SUPPORT_DATABASE_URL = get_database_url()


def _service() -> SupportService:
    return SupportService(SUPPORT_DATABASE_URL)


@tool
def lookup_customer(query: str) -> str:
    """Look up a customer by email address or full name. Returns customer profile and loyalty tier."""
    customer = _service().lookup_customer(query)
    if not customer:
        return f"No customer found matching '{query}'. Please verify the email or name."
    return (
        f"Customer found:\n"
        f"  ID: {customer.id}\n"
        f"  Name: {customer.name}\n"
        f"  Email: {customer.email}\n"
        f"  Phone: {customer.phone}\n"
        f"  Loyalty Tier: {customer.loyalty_tier}\n"
        f"  Annual Spend: ${customer.annual_spend:.2f}"
    )


@tool
def get_order_details(customer_query: str, order_id: str) -> str:
    """Retrieve an order only when it belongs to the supplied customer name or email."""
    order = _service().get_order(
        customer_query=customer_query,
        order_id=order_id,
    )
    if not order:
        return "No matching order was found for the supplied customer and Order ID."
    return (
        f"Order Details:\n"
        f"  Order ID: {order.order_id}\n"
        f"  Customer: {order.customer_name} ({order.customer_email}) — "
        f"{order.loyalty_tier} tier\n"
        f"  Product: {order.product} | Size: {order.size}\n"
        f"  Price: ${order.price:.2f} | Discount: {order.discount_pct}%\n"
        f"  Delivery Date: {order.delivery_date}\n"
        f"  Order Status: {order.status}\n"
        f"  Item Condition: {order.condition}\n"
        f"  Has Receipt/Order ID: {'Yes' if order.has_receipt else 'No'}\n"
        f"  Defective: {'Yes' if order.is_defective else 'No'}\n"
        f"  Current Refund Status: {order.refund_status}"
    )
