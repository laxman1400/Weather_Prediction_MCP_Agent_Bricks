"""
Weather Prediction MCP server for Databricks Apps.

Patterned after the Day-3 FastMCP server:
    Agent Bricks -> MCP tools -> weather_broker.py -> Open-Meteo REST API

The MCP tools are deliberately thin. All HTTP calls, geocoding, parsing,
weather-code translation and recommendation logic live in weather_broker.py.

Run locally:
    pip install -r requirements.txt
    python weather_mcp_server.py
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from fastmcp import FastMCP

import weather_broker


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-prediction-mcp")

mcp = FastMCP("weather-prediction")


def _clean_error(exc: Exception) -> dict[str, Any]:
    """Return an agent-friendly error instead of exposing a stack trace."""
    logger.warning("Weather tool failed: %s", exc)
    return {
        "status": "error",
        "error_type": exc.__class__.__name__,
        "message": str(exc),
    }


def _safe_call(function: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return function(*args, **kwargs)
    except weather_broker.WeatherBrokerError as exc:
        return _clean_error(exc)
    except Exception:
        logger.exception("Unexpected weather tool failure")
        return {
            "status": "error",
            "error_type": "UnexpectedError",
            "message": "The weather service could not complete the request.",
        }


@mcp.tool
def get_current_weather(location: str) -> dict:
    """
    Get current weather conditions for a location.

    Use this tool for questions about weather right now or current conditions.

    Args:
        location: City/place/postal code such as "Chicago, IL", or coordinates
            such as "41.8781,-87.6298".

    Returns:
        A dict with resolved location, observation time, temperature,
        apparent temperature, humidity, precipitation, wind speed/gusts,
        and readable weather conditions. Temperatures are Fahrenheit,
        wind is mph, and precipitation is inches.
    """
    return _safe_call(weather_broker.get_current_weather, location)


@mcp.tool
def get_forecast(location: str, days: int = 5) -> dict:
    """
    Get a multi-day weather forecast for a location.

    Use this tool for questions about tomorrow, upcoming days, weekends,
    rain chances, temperatures, or general future weather.

    Args:
        location: City/place/postal code such as "Austin, TX", or coordinates.
        days: Number of forecast days to return. Values are clamped to 1-16.

    Returns:
        A dict containing one record per day with high/low temperature,
        precipitation probability/amount, conditions, wind, gusts,
        sunrise, and sunset.
    """
    return _safe_call(weather_broker.get_forecast, location, days)


@mcp.tool
def get_travel_recommendation(location: str, date: str) -> dict:
    """
    Make a simple weather-based planning recommendation for a date.

    Unlike a raw forecast passthrough, this tool applies deterministic rules:
    an umbrella is recommended at >=40% precipitation probability (or >=0.05
    inches forecast precipitation); a jacket is recommended when the low is
    <=55 F; and outdoor conditions are rated good/fair/poor using rain, wind,
    heat and cold thresholds.

    Args:
        location: City/place/postal code such as "Minneapolis, MN", or coordinates.
        date: "today", "tomorrow", or an ISO date in YYYY-MM-DD format that falls
            within the available forecast window.

    Returns:
        A dict containing the forecast for the selected date plus
        umbrella_needed, jacket_recommended, outdoor_rating,
        recommendations, and reasoning.
    """
    return _safe_call(weather_broker.get_travel_recommendation, location, date)


@mcp.tool
def health() -> dict:
    """
    Check whether the Weather Prediction MCP server is running.

    Returns:
        Basic service status and provider information.
    """
    return {
        "status": "ok",
        "service": "weather-prediction-mcp",
        "provider": "Open-Meteo",
        "authentication": "none",
    }


if __name__ == "__main__":
    # Databricks Apps route external traffic to DATABRICKS_APP_PORT.
    # FastMCP HTTP transport provides the streamable-HTTP MCP endpoint.
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    mcp.run(transport="http", host="0.0.0.0", port=port)
