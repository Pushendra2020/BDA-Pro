"""Analytics service functions reused by the HTTP API."""

from customer_analytics import CustomerAnalytics


def get_overview(analytics: CustomerAnalytics):
    return analytics.get_overall_statistics()


def get_categories(analytics: CustomerAnalytics):
    return {"categories": analytics.get_revenue_by_category()}


def get_top_customers(analytics: CustomerAnalytics, limit: int = 10):
    return {"customers": analytics.get_top_customers(limit)["by_total_spending"]}


def get_activity(analytics: CustomerAnalytics):
    return analytics.get_activity_statistics()
