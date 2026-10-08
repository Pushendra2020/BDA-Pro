"""Customer and Customer 360 service functions."""

from customer_analytics import CustomerAnalytics


def get_profile(analytics: CustomerAnalytics, customer_id: str):
    return analytics.get_customer_profile(customer_id)


def get_customer_360(analytics: CustomerAnalytics, customer_id: str):
    return analytics.get_customer_360(customer_id)
