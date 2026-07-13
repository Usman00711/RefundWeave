"""Repeatable seed script for the migrated customer-support database."""

import argparse
from datetime import date, timedelta

from sqlalchemy import delete, func, select

from infrastructure.database import get_database_url, get_session_factory
from infrastructure.models import (
    Customer,
    EscalationTicket,
    Order,
    RefundEvent,
    RefundRequest,
)


def get_date(days_ago: int) -> date:
    return date.today() - timedelta(days=days_ago)


CUSTOMERS = [
    # id, name, email, phone, loyalty_tier, annual_spend
    (1,  "Alice Johnson",    "alice@email.com",    "555-0101", "Gold",     650.00),
    (2,  "Bob Martinez",     "bob@email.com",      "555-0102", "Standard", 120.00),
    (3,  "Carol White",      "carol@email.com",    "555-0103", "Platinum", 1250.00),
    (4,  "David Kim",        "david@email.com",    "555-0104", "Standard",  80.00),
    (5,  "Emma Davis",       "emma@email.com",     "555-0105", "Gold",     720.00),
    (6,  "Frank Thomas",     "frank@email.com",    "555-0106", "Standard", 200.00),
    (7,  "Grace Lee",        "grace@email.com",    "555-0107", "Standard",  45.00),
    (8,  "Henry Brown",      "henry@email.com",    "555-0108", "Standard", 310.00),
    (9,  "Isabella Garcia",  "isabella@email.com", "555-0109", "Gold",     580.00),
    (10, "James Wilson",     "james@email.com",    "555-0110", "Standard",  95.00),
    (11, "Karen Moore",      "karen@email.com",    "555-0111", "Standard", 160.00),
    (12, "Liam Taylor",      "liam@email.com",     "555-0112", "Platinum", 1800.00),
    (13, "Mia Anderson",     "mia@email.com",      "555-0113", "Standard",  55.00),
    (14, "Noah Jackson",     "noah@email.com",     "555-0114", "Standard", 230.00),
    (15, "Olivia Harris",    "olivia@email.com",   "555-0115", "Gold",     510.00),
]

ORDERS = [
    # id, customer_id, product, size, price, discount_pct, delivery_date, status, condition, has_receipt, is_defective
    ("ORD-001", 1,  "Air Stride Pro",        10,  129.99,  0,  get_date(20), "delivered", "unworn",  True,  False),  # Alice - valid refund (Gold, 20 days)
    ("ORD-002", 2,  "Classic Runner",         9,   89.99,  0,  get_date(45), "delivered", "worn",    True,  False),  # Bob - worn + 45 days (deny)
    ("ORD-003", 3,  "Urban Glide X",         11,  159.99,  0,  get_date(10), "delivered", "unworn",  True,  False),  # Carol - valid (Platinum)
    ("ORD-004", 4,  "Trail Blazer 2000",      8,   74.99, 25,  get_date(5),  "delivered", "unworn",  True,  False),  # David - FINAL SALE (deny)
    ("ORD-005", 5,  "Velocity Sprint",       10,  199.99,  0,  get_date(40), "delivered", "unworn",  True,  False),  # Emma - within Gold 45-day window
    ("ORD-006", 6,  "Canvas Daily",           9,   59.99,  0,  get_date(15), "delivered", "worn",    True,  False),  # Frank - worn (deny)
    ("ORD-007", 7,  "Night Racer Elite",      7,  149.99,  0,  get_date(12), "delivered", "unworn",  False, False),  # Grace - no receipt (deny)
    ("ORD-008", 8,  "Cloud Walker Pro",      12,  109.99,  0,  get_date(25), "delivered", "unworn",  True,  False),  # Henry - valid standard refund
    ("ORD-009", 9,  "Flex Runner",           10,   99.99,  0,  get_date(30), "delivered", "unworn",  True,  False),  # Isabella - exactly 30 days (edge, Gold 45-day = valid)
    ("ORD-010", 10, "Stealth Trainer",        9,  179.99,  0,  get_date(60), "delivered", "unworn",  True,  False),  # James - 60 days, standard (deny)
    ("ORD-011", 11, "Sole Signature Slip-On", 8,   49.99, 30,  get_date(3),  "delivered", "unworn",  True,  False),  # Karen - FINAL SALE 30% off (deny)
    ("ORD-012", 12, "Marathon Master",       11,  249.99,  0,  get_date(55), "delivered", "unworn",  True,  False),  # Liam - Platinum 60-day window (valid)
    ("ORD-013", 13, "Custom Kicks",          10,  300.00,  0,  get_date(8),  "delivered", "unworn",  True,  False),  # Mia - customized shoes (deny)
    ("ORD-014", 14, "Pavement Pounder",       9,  119.99,  0,  get_date(18), "delivered", "unworn",  True,  True),   # Noah - defective within 90 days (valid)
    ("ORD-015", 15, "Air Stride Pro",        10,  129.99,  0,  get_date(35), "delivered", "unworn",  True,  False),  # Olivia - Gold 45-day (valid)
]


def seed(*, reset: bool = False, database_url: str | None = None) -> bool:
    """Seed an empty database, or reset all demo records when explicitly requested."""
    session_factory = get_session_factory(database_url or get_database_url())
    with session_factory.begin() as session:
        existing = session.scalar(select(func.count()).select_from(Customer))
        if existing and not reset:
            print("Seed skipped: customer data already exists. Use --reset to restore demo data.")
            return False

        if reset:
            session.execute(delete(RefundEvent))
            session.execute(delete(RefundRequest))
            session.execute(delete(EscalationTicket))
            session.execute(delete(Order))
            session.execute(delete(Customer))

        session.add_all(
            Customer(
                id=customer[0],
                name=customer[1],
                email=customer[2],
                phone=customer[3],
                loyalty_tier=customer[4],
                annual_spend=customer[5],
            )
            for customer in CUSTOMERS
        )
        session.flush()
        session.add_all(
            Order(
                order_id=order[0],
                customer_id=order[1],
                product=order[2],
                size=order[3],
                price=order[4],
                discount_pct=order[5],
                delivery_date=order[6],
                status=order[7],
                condition=order[8],
                has_receipt=order[9],
                is_defective=order[10],
                refund_status="none",
            )
            for order in ORDERS
        )

    print(f"Database seeded: {len(CUSTOMERS)} customers | {len(ORDERS)} orders")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete transactional demo data and restore all seed scenarios.",
    )
    arguments = parser.parse_args()
    seed(reset=arguments.reset)
