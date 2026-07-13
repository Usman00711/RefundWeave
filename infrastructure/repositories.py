"""SQLAlchemy repositories used by application services."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from domain.refunds import OrderPolicyFacts
from infrastructure.models import Customer, Order


class SupportRepository:
    def __init__(self, session: Session):
        self.session = session

    def lookup_customer(self, query: str) -> Customer | None:
        normalized = query.strip().casefold()
        statement = select(Customer).where(
            or_(
                func.lower(Customer.email) == normalized,
                func.lower(Customer.name) == normalized,
            )
        )
        return self.session.scalar(statement)

    def get_owned_order(
        self,
        *,
        customer_query: str,
        order_id: str,
    ) -> tuple[Order, Customer] | None:
        normalized_customer = customer_query.strip().casefold()
        statement = (
            select(Order, Customer)
            .join(Customer, Order.customer_id == Customer.id)
            .where(
                func.upper(Order.order_id) == order_id.strip().upper(),
                or_(
                    func.lower(Customer.email) == normalized_customer,
                    func.lower(Customer.name) == normalized_customer,
                ),
            )
        )
        return self.session.execute(statement).one_or_none()

    def get_policy_facts(
        self,
        *,
        order_id: str,
        for_update: bool = False,
    ) -> OrderPolicyFacts | None:
        statement = (
            select(Order, Customer)
            .join(Customer, Order.customer_id == Customer.id)
            .where(func.upper(Order.order_id) == order_id.strip().upper())
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.execute(statement).one_or_none()
        if row is None:
            return None
        order, customer = row
        return OrderPolicyFacts(
            order_id=order.order_id,
            customer_name=customer.name,
            customer_email=customer.email,
            loyalty_tier=customer.loyalty_tier,
            product=order.product,
            price=order.price,
            discount_pct=order.discount_pct,
            delivery_date=order.delivery_date,
            order_status=order.status,
            condition=order.condition,
            has_receipt=order.has_receipt,
            is_defective=order.is_defective,
            refund_status=order.refund_status,
        )

    def get_order_for_update(self, order_id: str) -> Order | None:
        statement = (
            select(Order)
            .where(func.upper(Order.order_id) == order_id.strip().upper())
            .with_for_update()
        )
        return self.session.scalar(statement)
