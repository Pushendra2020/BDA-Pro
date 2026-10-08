"""Activity service functions using targeted HBase prefix scans."""

from customer_analytics import CustomerAnalytics


def get_customer_activity(analytics: CustomerAnalytics, customer_id: str):
    return analytics.get_customer_activity(customer_id)
