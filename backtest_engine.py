"""
Backtest Engine - Core analysis and backtesting logic.

Uses real stock data from yfinance and applies technical analysis
indicators to generate probability-based analysis using only data
available at each point in time (no look-ahead bias).

This engine does NOT recommend stocks. It analyzes historical patterns
and presents statistical probabilities for price movements.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Universe of stocks to analyze - major stocks across sectors
STOCK_UNIVERSE = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSM", "AVGO", "ORCL", "CRM"],
    "Finance": ["JPM", "BAC", "GS", "V", "MA", "BRK-B", "MS", "C", "AXP", "BLK"],
    "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "DHR", "BMY"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "DVN"],
    "Consumer": ["WMT", "PG", "KO", "PEP", "COST", "HD", "MCD", "NKE", "SBUX", "TGT"],
    "Industrial": ["CAT", "DE", "HON", "UPS", "BA", "GE", "RTX", "LMT", "MMM", "FDX"],
    "Semiconductors": ["NVDA", "AMD", "INTC", "QCOM", "MU", "LRCX", "AMAT", "KLAC", "MRVL", "ON"],
}

# Flatten to unique tickers
ALL_TICKERS = list(set(
    ticker for tickers in STOCK_UNIVERSE.values() for ticker in tickers
))


class BacktestEngine:
    def __init__(self):
        self._cache = {}
        self._backtest_results = None
        self._statistics = None

    def _fetch_stock_data(self, ticker, start_date, end_date):
        """Fetch historical stock data. Uses cache to avoid repeated API calls."""
        cache_key = f"{ticker}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_date, end=end_date)
            if df.empty:
                return None
            self._cache[cache_key] = df
            return df
        except Exception:
            return None

    def _compute_indicators(self, df):
        """
        Compute technical indicators from price data.
        These are the signals used to rank stocks at each point in time.
        """
        if df is None or len(df) < 20:
            return None

        indicators = {}

        # Momentum: 1-month and 3-month returns
        if len(df) >= 21:
            indicators["momentum_1m"] = (df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1) * 100
        if len(df) >= 63:
            indicators["momentum_3m"] = (df["Close"].iloc[-1] / df["Close"].iloc[-63] - 1) * 100

        # Moving averages
        indicators["sma_20"] = df["Close"].rolling(20).mean().iloc[-1]
        indicators["sma_50"] = df["Close"].rolling(50).mean().iloc[-1] if len(df) >= 50 else None
        indicators["price"] = df["Close"].iloc[-1]

        # Price relative to SMA (trend strength)
        indicators["price_vs_sma20"] = (indicators["price"] / indicators["sma_20"] - 1) * 100

        if indicators["sma_50"] is not None:
            indicators["price_vs_sma50"] = (indicators["price"] / indicators["sma_50"] - 1) * 100
            indicators["sma_20_vs_50"] = (indicators["sma_20"] / indicators["sma_50"] - 1) * 100

        # Volatility (lower is better for risk-adjusted returns)
        indicators["volatility"] = df["Close"].pct_change().std() * np.sqrt(252) * 100

        # RSI (14-day)
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else 100
        indicators["rsi"] = 100 - (100 / (1 + rs))

        # Volume trend
        if len(df) >= 20:
            recent_vol = df["Volume"].iloc[-5:].mean()
            avg_vol = df["Volume"].iloc[-20:].mean()
            indicators["volume_trend"] = (recent_vol / avg_vol - 1) * 100 if avg_vol > 0 else 0

        return indicators

    def _score_stock(self, indicators):
        """
        Score a stock based on its technical indicators.
        Higher score = stronger bullish signal probability.
        """
        if indicators is None:
            return -999

        score = 0

        # Momentum score (weighted heavily)
        mom_1m = indicators.get("momentum_1m", 0)
        mom_3m = indicators.get("momentum_3m", 0)
        score += mom_1m * 0.3  # Recent momentum
        score += mom_3m * 0.2  # Longer-term momentum

        # Trend alignment score
        price_vs_sma20 = indicators.get("price_vs_sma20", 0)
        if price_vs_sma20 > 0:
            score += min(price_vs_sma20, 10) * 0.5  # Above SMA20 is bullish, cap contribution

        sma_cross = indicators.get("sma_20_vs_50")
        if sma_cross is not None and sma_cross > 0:
            score += min(sma_cross, 10) * 0.3  # Golden cross signal

        # RSI - prefer stocks not overbought
        rsi = indicators.get("rsi", 50)
        if 30 <= rsi <= 70:
            score += 2  # Healthy RSI range
        elif rsi < 30:
            score += 3  # Oversold = potential opportunity
        else:
            score -= 1  # Overbought = risky

        # Volume confirmation
        vol_trend = indicators.get("volume_trend", 0)
        if vol_trend > 0 and mom_1m > 0:
            score += 1  # Rising volume + rising price = confirmation

        # Risk penalty
        volatility = indicators.get("volatility", 20)
        if volatility > 40:
            score -= 2  # High volatility penalty

        return round(score, 2)

    def _calculate_probability(self, indicators, score):
        """
        Convert technical score and indicators into a probability estimate
        for positive price movement in the next month.

        This uses a logistic-style mapping: higher scores map to higher
        probability of upward movement. The base rate for any stock going
        up in a given month is ~55% (historical average for S&P 500 stocks).
        """
        BASE_RATE = 0.55  # Historical base rate of monthly positive returns

        if indicators is None:
            return BASE_RATE

        # Logistic transformation of score to probability
        # Score of 0 -> base rate, positive scores increase probability
        adjusted = 1 / (1 + np.exp(-score / 10))

        # Blend with base rate to avoid extreme predictions
        probability = 0.4 * adjusted + 0.6 * BASE_RATE

        # Signal confidence based on indicator alignment
        signals_aligned = 0
        total_signals = 0

        # Check momentum alignment
        mom_1m = indicators.get("momentum_1m", 0)
        mom_3m = indicators.get("momentum_3m", 0)
        total_signals += 2
        if mom_1m > 0:
            signals_aligned += 1
        if mom_3m > 0:
            signals_aligned += 1

        # Check trend alignment
        total_signals += 1
        if indicators.get("price_vs_sma20", 0) > 0:
            signals_aligned += 1

        if indicators.get("sma_20_vs_50") is not None:
            total_signals += 1
            if indicators["sma_20_vs_50"] > 0:
                signals_aligned += 1

        # RSI in healthy range
        rsi = indicators.get("rsi", 50)
        total_signals += 1
        if 30 <= rsi <= 65:
            signals_aligned += 1

        confidence = signals_aligned / total_signals if total_signals > 0 else 0.5

        return {
            "up_probability": round(min(max(probability, 0.15), 0.85), 3),
            "confidence": round(confidence, 3),
            "signals_aligned": signals_aligned,
            "total_signals": total_signals,
        }

    def analyze_month(self, analysis_date):
        """
        Analyze stocks for a given month using ONLY data available up to that date.
        This is the key anti-bias mechanism. Returns probability analysis, not recommendations.
        """
        if isinstance(analysis_date, str):
            analysis_date = datetime.strptime(analysis_date, "%Y-%m")

        # We fetch 6 months of history ending at the analysis date
        end_date = analysis_date.strftime("%Y-%m-%d")
        start_date = (analysis_date - relativedelta(months=6)).strftime("%Y-%m-%d")

        results = []
        for ticker in ALL_TICKERS:
            df = self._fetch_stock_data(ticker, start_date, end_date)
            if df is None or df.empty:
                continue

            indicators = self._compute_indicators(df)
            if indicators is None:
                continue

            score = self._score_stock(indicators)
            prob = self._calculate_probability(indicators, score)

            # Find which sector this ticker belongs to
            sector = "Other"
            for sec, tickers in STOCK_UNIVERSE.items():
                if ticker in tickers:
                    sector = sec
                    break

            results.append({
                "ticker": ticker,
                "sector": sector,
                "score": score,
                "price_at_analysis": round(indicators["price"], 2),
                "up_probability": prob["up_probability"],
                "confidence": prob["confidence"],
                "signals_aligned": prob["signals_aligned"],
                "total_signals": prob["total_signals"],
                "momentum_1m": round(indicators.get("momentum_1m", 0), 2),
                "momentum_3m": round(indicators.get("momentum_3m", 0), 2),
                "rsi": round(indicators.get("rsi", 50), 1),
                "volatility": round(indicators.get("volatility", 0), 1),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return {
            "date": analysis_date.strftime("%Y-%m"),
            "analysis_date": end_date,
            "stocks_analyzed": len(results),
            "analysis": results,
        }

    def _evaluate_pick(self, ticker, rec_date, price_at_rec):
        """
        Evaluate how a top-scored stock actually performed 1 month after analysis.
        """
        start = rec_date
        end = rec_date + relativedelta(months=1) + timedelta(days=5)

        df = self._fetch_stock_data(ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df is None or df.empty:
            return None

        # Get the price approximately 1 month later
        target_date = rec_date + relativedelta(months=1)
        future_prices = df[df.index >= pd.Timestamp(target_date)]

        if future_prices.empty:
            # Use last available price
            end_price = df["Close"].iloc[-1]
        else:
            end_price = future_prices["Close"].iloc[0]

        return_pct = (end_price / price_at_rec - 1) * 100
        return {
            "end_price": round(float(end_price), 2),
            "return_pct": round(float(return_pct), 2),
            "positive": return_pct > 0,
        }

    def run_full_backtest(self, months_back=12, top_n=5):
        """
        Run the full backtest: for each month going back, analyze stocks
        and track actual performance of top-scored stocks.
        """
        today = datetime.now()
        monthly_results = []

        for i in range(months_back, 0, -1):
            analysis_date = today - relativedelta(months=i)
            # Set to first of month
            analysis_date = analysis_date.replace(day=1)

            month_analysis = self.analyze_month(analysis_date)
            top_picks = month_analysis["analysis"][:top_n]

            # Evaluate each top-scored stock
            evaluated = []
            for pick in top_picks:
                perf = self._evaluate_pick(
                    pick["ticker"],
                    analysis_date,
                    pick["price_at_analysis"],
                )
                entry = {**pick}
                if perf:
                    entry["end_price"] = perf["end_price"]
                    entry["return_pct"] = perf["return_pct"]
                    entry["positive"] = perf["positive"]
                else:
                    entry["end_price"] = None
                    entry["return_pct"] = None
                    entry["positive"] = None
                evaluated.append(entry)

            avg_return = np.mean([e["return_pct"] for e in evaluated if e["return_pct"] is not None])
            positive_count = sum(1 for e in evaluated if e.get("positive"))
            total_evaluated = sum(1 for e in evaluated if e["return_pct"] is not None)

            monthly_results.append({
                "month": analysis_date.strftime("%Y-%m"),
                "analysis": evaluated,
                "avg_return": round(float(avg_return), 2) if not np.isnan(avg_return) else 0,
                "positive_rate": round(positive_count / total_evaluated * 100, 1) if total_evaluated > 0 else 0,
                "total_picks": len(evaluated),
            })

        # Compute overall statistics
        all_returns = []
        for m in monthly_results:
            for r in m["analysis"]:
                if r["return_pct"] is not None:
                    all_returns.append(r["return_pct"])

        statistics = self._compute_statistics(monthly_results, all_returns)

        self._backtest_results = monthly_results
        self._statistics = statistics

        return {
            "monthly_results": monthly_results,
            "statistics": statistics,
        }

    def _compute_statistics(self, monthly_results, all_returns):
        """Compute comprehensive backtest statistics including probability accuracy."""
        if not all_returns:
            return {"error": "No returns data available"}

        positive_returns = [r for r in all_returns if r > 0]
        negative_returns = [r for r in all_returns if r <= 0]

        # Probability accuracy: did stocks with >60% probability actually go up?
        probability_buckets = {"high": [], "medium": [], "low": []}
        for m in monthly_results:
            for r in m["analysis"]:
                if r["return_pct"] is not None and "up_probability" in r:
                    prob = r["up_probability"]
                    actual_up = r["return_pct"] > 0
                    if prob >= 0.65:
                        probability_buckets["high"].append(actual_up)
                    elif prob >= 0.50:
                        probability_buckets["medium"].append(actual_up)
                    else:
                        probability_buckets["low"].append(actual_up)

        probability_accuracy = {}
        for bucket, outcomes in probability_buckets.items():
            if outcomes:
                probability_accuracy[bucket] = {
                    "predicted_direction_correct": round(sum(outcomes) / len(outcomes) * 100, 1),
                    "sample_size": len(outcomes),
                }

        # Sector performance
        sector_returns = {}
        for m in monthly_results:
            for r in m["analysis"]:
                if r["return_pct"] is not None:
                    sector = r.get("sector", "Other")
                    if sector not in sector_returns:
                        sector_returns[sector] = []
                    sector_returns[sector].append(r["return_pct"])

        sector_stats = {}
        for sector, returns in sector_returns.items():
            sector_stats[sector] = {
                "avg_return": round(float(np.mean(returns)), 2),
                "hit_rate": round(sum(1 for r in returns if r > 0) / len(returns) * 100, 1),
                "count": len(returns),
            }

        # Monthly progression
        cumulative = 0
        monthly_cumulative = []
        for m in monthly_results:
            cumulative += m["avg_return"]
            monthly_cumulative.append({
                "month": m["month"],
                "monthly_return": m["avg_return"],
                "cumulative_return": round(cumulative, 2),
            })

        statistics = {
            "total_analyses": len(all_returns),
            "months_analyzed": len(monthly_results),
            "avg_return_per_recommendation": round(float(np.mean(all_returns)), 2),
            "median_return": round(float(np.median(all_returns)), 2),
            "hit_rate": round(len(positive_returns) / len(all_returns) * 100, 1),
            "avg_positive_return": round(float(np.mean(positive_returns)), 2) if positive_returns else 0,
            "avg_negative_return": round(float(np.mean(negative_returns)), 2) if negative_returns else 0,
            "best_pick": round(float(max(all_returns)), 2),
            "worst_pick": round(float(min(all_returns)), 2),
            "std_deviation": round(float(np.std(all_returns)), 2),
            "positive_months": sum(1 for m in monthly_results if m["avg_return"] > 0),
            "cumulative_return": round(cumulative, 2),
            "sector_performance": sector_stats,
            "monthly_progression": monthly_cumulative,
            "probability_accuracy": probability_accuracy,
        }

        return statistics

    def get_cached_statistics(self):
        """Return cached statistics from last backtest run."""
        if self._statistics:
            return self._statistics
        return {"error": "No backtest has been run yet. Call /api/run-backtest first."}

    def get_stock_history(self, ticker, months=12):
        """Get price history for a specific stock."""
        end_date = datetime.now()
        start_date = end_date - relativedelta(months=months)

        df = self._fetch_stock_data(
            ticker,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )

        if df is None or df.empty:
            return {"error": f"No data found for {ticker}"}

        prices = []
        for date, row in df.iterrows():
            prices.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })

        return {
            "ticker": ticker,
            "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "data_points": len(prices),
            "prices": prices,
        }
