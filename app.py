"""
INvest - Stock Analysis Backtesting Application

This application performs historical stock analysis by:
1. Fetching real stock price data month by month
2. Running technical analysis based on data available at each point in time
3. Tracking recommendation performance over time
4. Displaying statistics and event impact analysis
"""

from flask import Flask, render_template, jsonify, request
import json
from datetime import datetime

from backtest_engine import BacktestEngine
from events_tracker import EventsTracker

app = Flask(__name__)
engine = BacktestEngine()
events_tracker = EventsTracker()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/run-backtest", methods=["POST"])
def run_backtest():
    """Run the full backtest from start_date going forward month by month."""
    data = request.get_json() or {}
    months_back = data.get("months_back", 12)
    top_n = data.get("top_n", 5)

    results = engine.run_full_backtest(months_back=months_back, top_n=top_n)
    return jsonify(results)


@app.route("/api/monthly-analysis/<year_month>")
def monthly_analysis(year_month):
    """Get analysis for a specific month (format: YYYY-MM)."""
    try:
        date = datetime.strptime(year_month, "%Y-%m")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM"}), 400

    analysis = engine.analyze_month(date)
    return jsonify(analysis)


@app.route("/api/events")
def get_events():
    """Get major market events in the backtest period."""
    return jsonify(events_tracker.get_all_events())


@app.route("/api/statistics")
def get_statistics():
    """Get overall backtest statistics."""
    stats = engine.get_cached_statistics()
    return jsonify(stats)


@app.route("/api/stock-history/<ticker>")
def stock_history(ticker):
    """Get price history for a specific stock."""
    months = request.args.get("months", 12, type=int)
    history = engine.get_stock_history(ticker.upper(), months)
    return jsonify(history)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
