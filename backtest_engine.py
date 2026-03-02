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

# Sector lookup for fast access
TICKER_TO_SECTOR = {}
for _sector, _tickers in STOCK_UNIVERSE.items():
    for _t in _tickers:
        TICKER_TO_SECTOR[_t] = _sector


class BacktestEngine:
    def __init__(self):
        self._cache = {}
        self._bulk_data = {}
        self._backtest_results = None
        self._statistics = None

    def _resolve_tickers(self, sector=None, tickers=None):
        """Resolve which tickers to analyze based on filters."""
        if tickers:
            if isinstance(tickers, str):
                tickers = [t.strip().upper() for t in tickers.split(",")]
            return tickers
        if sector:
            return STOCK_UNIVERSE.get(sector, ALL_TICKERS)
        return ALL_TICKERS

    def _bulk_download(self, tickers, start_date, end_date):
        """Download all tickers at once using yf.download for much faster fetching."""
        try:
            df = yf.download(
                tickers,
                start=start_date,
                end=end_date,
                group_by="ticker",
                threads=True,
            )
            if df is None or df.empty:
                return

            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        ticker_df = df.copy()
                    else:
                        ticker_df = df[ticker].copy()

                    # Flatten MultiIndex columns if present
                    if hasattr(ticker_df.columns, 'nlevels') and ticker_df.columns.nlevels > 1:
                        ticker_df.columns = ticker_df.columns.get_level_values(-1)

                    # Validate required columns exist
                    if "Close" not in ticker_df.columns:
                        continue

                    ticker_df = ticker_df.dropna(subset=["Close"])
                    if not ticker_df.empty:
                        self._bulk_data[ticker] = ticker_df
                except (KeyError, Exception):
                    continue
        except Exception:
            pass

    def _fetch_stock_data(self, ticker, start_date, end_date):
        """Fetch historical stock data. Uses bulk pre-downloaded data when available."""
        cache_key = f"{ticker}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try to slice from bulk data first
        if ticker in self._bulk_data:
            try:
                bulk = self._bulk_data[ticker]
                sliced = bulk.loc[start_date:end_date]
                if not sliced.empty:
                    self._cache[cache_key] = sliced
                    return sliced
            except Exception:
                pass

        # Fallback to individual download
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
        """
        BASE_RATE = 0.55

        if indicators is None:
            return BASE_RATE

        adjusted = 1 / (1 + np.exp(-score / 10))
        probability = 0.4 * adjusted + 0.6 * BASE_RATE

        signals_aligned = 0
        total_signals = 0

        mom_1m = indicators.get("momentum_1m", 0)
        mom_3m = indicators.get("momentum_3m", 0)
        total_signals += 2
        if mom_1m > 0:
            signals_aligned += 1
        if mom_3m > 0:
            signals_aligned += 1

        total_signals += 1
        if indicators.get("price_vs_sma20", 0) > 0:
            signals_aligned += 1

        if indicators.get("sma_20_vs_50") is not None:
            total_signals += 1
            if indicators["sma_20_vs_50"] > 0:
                signals_aligned += 1

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

    def analyze_month(self, analysis_date, ticker_list=None):
        """
        Analyze stocks for a given month using ONLY data available up to that date.
        This is the key anti-bias mechanism.
        """
        if isinstance(analysis_date, str):
            analysis_date = datetime.strptime(analysis_date, "%Y-%m")

        end_date = analysis_date.strftime("%Y-%m-%d")
        start_date = (analysis_date - relativedelta(months=6)).strftime("%Y-%m-%d")

        tickers_to_analyze = ticker_list or ALL_TICKERS

        results = []
        for ticker in tickers_to_analyze:
            df = self._fetch_stock_data(ticker, start_date, end_date)
            if df is None or df.empty:
                continue

            indicators = self._compute_indicators(df)
            if indicators is None:
                continue

            score = self._score_stock(indicators)
            prob = self._calculate_probability(indicators, score)

            sector = TICKER_TO_SECTOR.get(ticker, "Other")

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

        target_date = rec_date + relativedelta(months=1)
        future_prices = df[df.index >= pd.Timestamp(target_date)]

        if future_prices.empty:
            end_price = df["Close"].iloc[-1]
        else:
            end_price = future_prices["Close"].iloc[0]

        return_pct = (end_price / price_at_rec - 1) * 100
        return {
            "end_price": round(float(end_price), 2),
            "return_pct": round(float(return_pct), 2),
            "positive": return_pct > 0,
        }

    def run_full_backtest(self, months_back=12, top_n=5, sector=None, tickers=None):
        """
        Run the full backtest: for each month going back, analyze stocks
        and track actual performance of top-scored stocks.
        """
        today = datetime.now()
        monthly_results = []

        ticker_list = self._resolve_tickers(sector=sector, tickers=tickers)

        # Pre-download ALL stock data in one batch call
        earliest_analysis = (today - relativedelta(months=months_back)).replace(day=1)
        bulk_start = (earliest_analysis - relativedelta(months=6)).strftime("%Y-%m-%d")
        bulk_end = (today + timedelta(days=10)).strftime("%Y-%m-%d")
        self._bulk_download(ticker_list, bulk_start, bulk_end)

        for i in range(months_back, 0, -1):
            analysis_date = today - relativedelta(months=i)
            analysis_date = analysis_date.replace(day=1)

            month_analysis = self.analyze_month(analysis_date, ticker_list=ticker_list)
            top_picks = month_analysis["analysis"][:top_n]

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

        # Compute calibration from backtest results
        calibration = self._compute_calibration(monthly_results)

        # Generate forward prediction
        forward = self._predict_forward(top_n, ticker_list, calibration)

        self._backtest_results = monthly_results
        self._statistics = statistics

        return {
            "monthly_results": monthly_results,
            "statistics": statistics,
            "calibration": calibration,
            "forward_prediction": forward,
        }

    def _compute_calibration(self, monthly_results):
        """
        Compute regression calibration: how well did predicted probabilities
        match actual outcomes? Returns calibration factors to adjust forward predictions.
        """
        pairs = []
        for m in monthly_results:
            for r in m["analysis"]:
                if r["return_pct"] is not None and "up_probability" in r:
                    pairs.append({
                        "predicted": r["up_probability"],
                        "actual_up": 1 if r["return_pct"] > 0 else 0,
                        "actual_return": r["return_pct"],
                    })

        if len(pairs) < 5:
            return {"error": "Not enough data for calibration", "factor": 1.0, "pairs": len(pairs)}

        predicted = np.array([p["predicted"] for p in pairs])
        actual = np.array([p["actual_up"] for p in pairs])
        actual_returns = np.array([p["actual_return"] for p in pairs])

        if np.std(predicted) > 0.001:
            try:
                slope, intercept = np.polyfit(predicted, actual, 1)
                if np.isnan(slope) or np.isnan(intercept):
                    slope, intercept = 1.0, 0.0
            except Exception:
                slope, intercept = 1.0, 0.0
        else:
            slope, intercept = 1.0, 0.0

        predicted_outcomes = slope * predicted + intercept
        ss_res = np.sum((actual - predicted_outcomes) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0.001 else 0
        r_squared = max(r_squared, 0)  # Clamp negative R²

        buckets = {"high": [], "medium": [], "low": []}
        for p in pairs:
            if p["predicted"] >= 0.65:
                buckets["high"].append(p)
            elif p["predicted"] >= 0.50:
                buckets["medium"].append(p)
            else:
                buckets["low"].append(p)

        bucket_stats = {}
        for name, bucket_pairs in buckets.items():
            if bucket_pairs:
                avg_predicted = np.mean([p["predicted"] for p in bucket_pairs])
                actual_rate = np.mean([p["actual_up"] for p in bucket_pairs])
                avg_return = np.mean([p["actual_return"] for p in bucket_pairs])
                bucket_stats[name] = {
                    "count": len(bucket_pairs),
                    "avg_predicted_prob": round(float(avg_predicted), 3),
                    "actual_success_rate": round(float(actual_rate), 3),
                    "avg_actual_return": round(float(avg_return), 2),
                    "calibration_ratio": round(float(actual_rate / avg_predicted), 3) if avg_predicted > 0 else 1.0,
                }

        avg_predicted_prob = float(np.mean(predicted))
        actual_success_rate = float(np.mean(actual))
        overall_bias = actual_success_rate - avg_predicted_prob

        return {
            "slope": round(float(slope), 4),
            "intercept": round(float(intercept), 4),
            "r_squared": round(float(r_squared), 4),
            "total_pairs": len(pairs),
            "avg_predicted_prob": round(avg_predicted_prob, 3),
            "actual_success_rate": round(actual_success_rate, 3),
            "model_bias": round(float(overall_bias), 3),
            "avg_actual_return": round(float(np.mean(actual_returns)), 2),
            "buckets": bucket_stats,
        }

    def _predict_forward(self, top_n, ticker_list, calibration):
        """
        Generate forward prediction using current data + calibration from backtest.
        """
        today = datetime.now()
        analysis = self.analyze_month(today, ticker_list=ticker_list)

        top_picks = analysis["analysis"][:top_n]

        slope = calibration.get("slope", 1.0)
        intercept = calibration.get("intercept", 0.0)
        has_calibration = "error" not in calibration

        calibrated_picks = []
        for pick in top_picks:
            entry = {**pick}
            raw_prob = pick["up_probability"]

            if has_calibration:
                calibrated_prob = slope * raw_prob + intercept
                calibrated_prob = round(min(max(calibrated_prob, 0.10), 0.95), 3)
                entry["calibrated_probability"] = calibrated_prob
            else:
                entry["calibrated_probability"] = raw_prob

            calibrated_picks.append(entry)

        if calibrated_picks:
            avg_calibrated_prob = np.mean([p["calibrated_probability"] for p in calibrated_picks])
            avg_raw_prob = np.mean([p["up_probability"] for p in calibrated_picks])
            avg_score = np.mean([p["score"] for p in calibrated_picks])

            backtest_avg = calibration.get("avg_actual_return", 0)
            expected_return = backtest_avg * (avg_calibrated_prob / 0.55) if backtest_avg != 0 else 0

            bottom_line = {
                "avg_raw_probability": round(float(avg_raw_prob), 3),
                "avg_calibrated_probability": round(float(avg_calibrated_prob), 3),
                "avg_score": round(float(avg_score), 2),
                "expected_monthly_return": round(float(expected_return), 2),
                "model_confidence": calibration.get("r_squared", 0),
                "recommendation": _get_recommendation(avg_calibrated_prob, calibration.get("r_squared", 0)),
            }
        else:
            bottom_line = {"error": "No stocks to analyze"}

        return {
            "analysis_date": today.strftime("%Y-%m-%d"),
            "prediction_horizon": "1 month",
            "stocks_analyzed": analysis["stocks_analyzed"],
            "top_picks": calibrated_picks,
            "bottom_line": bottom_line,
        }

    def _compute_statistics(self, monthly_results, all_returns):
        """Compute comprehensive backtest statistics including probability accuracy."""
        if not all_returns:
            return {"error": "No returns data available"}

        positive_returns = [r for r in all_returns if r > 0]
        negative_returns = [r for r in all_returns if r <= 0]

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


def _get_recommendation(calibrated_prob, r_squared):
    """Generate a text recommendation based on calibrated probability and model confidence."""
    if r_squared < 0.01:
        confidence_text = "אמינות המודל נמוכה"
    elif r_squared < 0.1:
        confidence_text = "אמינות המודל בינונית"
    else:
        confidence_text = "אמינות המודל סבירה"

    if calibrated_prob >= 0.65:
        signal = "סיגנל חיובי חזק"
    elif calibrated_prob >= 0.55:
        signal = "סיגנל חיובי מתון"
    elif calibrated_prob >= 0.45:
        signal = "ניטרלי - אין כיוון ברור"
    elif calibrated_prob >= 0.35:
        signal = "סיגנל שלילי מתון"
    else:
        signal = "סיגנל שלילי חזק"

    return f"{signal} | {confidence_text}"
