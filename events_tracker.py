"""
Events Tracker - Tracks major geopolitical and economic events
that impact stock market performance.

This helps contextualize backtest results by showing which events
occurred during each period, explaining anomalies in returns.
"""

from datetime import datetime


class EventsTracker:
    """Track and provide information about major market-moving events."""

    # Major events from March 2025 to March 2026
    EVENTS = [
        {
            "date": "2025-03-01",
            "title": "US Tariff Escalation",
            "description": "New tariffs on Chinese goods escalated trade tensions, creating market uncertainty.",
            "impact": "negative",
            "severity": "medium",
            "sectors_affected": ["Technology", "Consumer", "Industrial"],
        },
        {
            "date": "2025-04-02",
            "title": "Liberation Day Tariffs",
            "description": "Major tariff announcement ('Liberation Day') triggered a significant market selloff. S&P 500 dropped sharply.",
            "impact": "negative",
            "severity": "high",
            "sectors_affected": ["Technology", "Consumer", "Industrial", "Finance"],
        },
        {
            "date": "2025-04-09",
            "title": "90-Day Tariff Pause",
            "description": "Announcement of 90-day pause on new tariffs led to massive market rally and recovery.",
            "impact": "positive",
            "severity": "high",
            "sectors_affected": ["Technology", "Consumer", "Industrial", "Finance"],
        },
        {
            "date": "2025-05-12",
            "title": "US-China Trade Deal Framework",
            "description": "Initial framework agreement between US and China on trade, reducing tariff rates.",
            "impact": "positive",
            "severity": "medium",
            "sectors_affected": ["Technology", "Industrial", "Semiconductors"],
        },
        {
            "date": "2025-06-18",
            "title": "Fed Rate Decision - Hold",
            "description": "Federal Reserve held rates steady, signaling patience amid trade uncertainty.",
            "impact": "neutral",
            "severity": "low",
            "sectors_affected": ["Finance"],
        },
        {
            "date": "2025-07-15",
            "title": "AI Chip Export Restrictions Eased",
            "description": "US eased some AI chip export restrictions, benefiting semiconductor companies.",
            "impact": "positive",
            "severity": "medium",
            "sectors_affected": ["Technology", "Semiconductors"],
        },
        {
            "date": "2025-09-17",
            "title": "Fed Rate Cut",
            "description": "Federal Reserve cut interest rates, boosting market sentiment.",
            "impact": "positive",
            "severity": "medium",
            "sectors_affected": ["Finance", "Technology", "Consumer"],
        },
        {
            "date": "2025-10-01",
            "title": "Middle East Tensions Escalation",
            "description": "Escalation in Middle East conflict increased oil prices and market volatility.",
            "impact": "negative",
            "severity": "medium",
            "sectors_affected": ["Energy", "Industrial"],
        },
        {
            "date": "2025-12-10",
            "title": "Year-End Rally",
            "description": "Traditional year-end rally driven by strong holiday retail data and tech earnings.",
            "impact": "positive",
            "severity": "low",
            "sectors_affected": ["Consumer", "Technology"],
        },
        {
            "date": "2026-01-20",
            "title": "New Administration Policies",
            "description": "New economic policy announcements created market uncertainty about regulatory changes.",
            "impact": "neutral",
            "severity": "medium",
            "sectors_affected": ["Finance", "Healthcare", "Energy"],
        },
        {
            "date": "2026-02-15",
            "title": "Iran Military Escalation",
            "description": "Military action against Iran caused sharp market selloff and oil price spike.",
            "impact": "negative",
            "severity": "high",
            "sectors_affected": ["Energy", "Industrial", "Finance", "Technology"],
        },
        {
            "date": "2026-02-25",
            "title": "Global Market Volatility",
            "description": "Ongoing geopolitical tensions kept markets volatile with increased uncertainty.",
            "impact": "negative",
            "severity": "medium",
            "sectors_affected": ["Finance", "Technology", "Consumer"],
        },
    ]

    def get_all_events(self):
        """Return all tracked events."""
        return {
            "events": self.EVENTS,
            "total": len(self.EVENTS),
            "period": "March 2025 - March 2026",
        }

    def get_events_for_month(self, year_month):
        """Get events that occurred in a specific month."""
        events = [
            e for e in self.EVENTS
            if e["date"].startswith(year_month)
        ]
        return events

    def get_events_by_impact(self, impact_type):
        """Filter events by impact type (positive/negative/neutral)."""
        return [e for e in self.EVENTS if e["impact"] == impact_type]

    def get_events_by_severity(self, severity):
        """Filter events by severity (high/medium/low)."""
        return [e for e in self.EVENTS if e["severity"] == severity]

    def get_event_context(self, date_str):
        """
        Get events within 2 weeks before and after a given date,
        useful for contextualizing a specific recommendation's performance.
        """
        target = datetime.strptime(date_str, "%Y-%m-%d")
        nearby = []
        for event in self.EVENTS:
            event_date = datetime.strptime(event["date"], "%Y-%m-%d")
            days_diff = abs((target - event_date).days)
            if days_diff <= 14:
                nearby.append({**event, "days_from_target": days_diff})
        return nearby
