from enum import Enum


class SubscriptionPlan(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ANNUAL = "annual"
