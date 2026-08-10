"""
Open-Meteo adapter for the Weather Prediction MCP server.

All external HTTP calls and response parsing live in this module.
The MCP tool layer imports these functions and stays intentionally thin.

Provider:
    Open-Meteo Geocoding API
    Open-Meteo Forecast API

Authentication:
    None required for the free/non-commercial Open-Meteo API.

Units:
    Temperature: Fahrenheit
    Wind: mph
    Precipitation: inches
"""

from __future__ import annotations

import os
import re
from datetime import date as Date
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

REQUEST_TIMEOUT_SECONDS = float(os.getenv("WEATHER_API_TIMEOUT_SECONDS", "15"))

# Helps disambiguate common "City, ST" U.S. inputs returned by geocoding.
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherBrokerError(RuntimeError):
    """Base exception for clean weather API failures."""


class LocationNotFoundError(WeatherBrokerError):
    """Raised when a location cannot be resolved."""


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {
            "User-Agent": "weather-prediction-mcp-agent/1.0",
            "Accept": "application/json",
        }
    )
    return session


_HTTP = _session()


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET JSON from an external weather endpoint with clean error handling."""
    try:
        response = _HTTP.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise WeatherBrokerError(f"Weather API request failed: {exc}") from exc
    except ValueError as exc:
        raise WeatherBrokerError("Weather API returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise WeatherBrokerError("Weather API returned an unexpected response format.")
    return payload


def _coordinates_from_text(location: str) -> tuple[float, float] | None:
    """Parse 'lat,lon' input if supplied."""
    match = re.fullmatch(
        r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*",
        location,
    )
    if not match:
        return None

    latitude = float(match.group(1))
    longitude = float(match.group(2))
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise LocationNotFoundError("Latitude/longitude is outside the valid range.")
    return latitude, longitude


def _candidate_score(
    candidate: dict[str, Any],
    city_hint: str,
    region_hint: str | None,
) -> tuple[int, int]:
    """Rank geocoding candidates so 'Chicago, IL' prefers Chicago, Illinois."""
    score = 0
    name = str(candidate.get("name") or "").strip()
    admin1 = str(candidate.get("admin1") or "").strip()
    country_code = str(candidate.get("country_code") or "").upper()

    if name.casefold() == city_hint.casefold():
        score += 100

    if region_hint:
        hint = region_hint.strip()
        hint_upper = hint.upper()
        expected_state = US_STATES.get(hint_upper)

        if expected_state and admin1.casefold() == expected_state.casefold():
            score += 80
            if country_code == "US":
                score += 20
        elif admin1 and admin1.casefold() == hint.casefold():
            score += 70
        elif hint_upper in {"US", "USA", "UNITED STATES"} and country_code == "US":
            score += 50

    population = int(candidate.get("population") or 0)
    return score, population


def resolve_location(location: str) -> dict[str, Any]:
    """
    Resolve a city/place/postal-code string or 'lat,lon' into coordinates.

    Returns:
        Dict with display_name, latitude, longitude, timezone and location metadata.
    """
    if not isinstance(location, str) or not location.strip():
        raise LocationNotFoundError("location must be a non-empty string.")

    raw = location.strip()
    coordinates = _coordinates_from_text(raw)
    if coordinates:
        latitude, longitude = coordinates
        return {
            "query": raw,
            "display_name": f"{latitude:.4f}, {longitude:.4f}",
            "name": None,
            "admin1": None,
            "country": None,
            "country_code": None,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": None,
        }

    parts = [part.strip() for part in raw.split(",", 1)]
    city_hint = parts[0]
    region_hint = parts[1] if len(parts) > 1 else None

    # Geocoding is generally more reliable when the primary place name is
    # searched separately and the state/country hint is used for ranking.
    payload = _get_json(
        GEOCODING_URL,
        {
            "name": city_hint,
            "count": 10,
            "language": "en",
            "format": "json",
        },
    )
    results = payload.get("results") or []
    if not results:
        # Retry the exact original text for postal codes or unusual names.
        payload = _get_json(
            GEOCODING_URL,
            {
                "name": raw,
                "count": 10,
                "language": "en",
                "format": "json",
            },
        )
        results = payload.get("results") or []

    if not results:
        raise LocationNotFoundError(
            f"Could not resolve location '{location}'. Try 'City, State' or 'lat,lon'."
        )

    best = max(
        results,
        key=lambda candidate: _candidate_score(candidate, city_hint, region_hint),
    )

    try:
        latitude = float(best["latitude"])
        longitude = float(best["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherBrokerError("Geocoding response did not include valid coordinates.") from exc

    name = str(best.get("name") or city_hint)
    admin1 = best.get("admin1")
    country = best.get("country")
    display_parts = [name]
    if admin1 and str(admin1).casefold() != name.casefold():
        display_parts.append(str(admin1))
    if country:
        display_parts.append(str(country))

    return {
        "query": raw,
        "display_name": ", ".join(display_parts),
        "name": name,
        "admin1": admin1,
        "country": country,
        "country_code": best.get("country_code"),
        "latitude": latitude,
        "longitude": longitude,
        "timezone": best.get("timezone"),
    }


def weather_code_to_text(code: Any) -> str:
    """Translate an Open-Meteo/WMO weather code into readable text."""
    try:
        numeric_code = int(code)
    except (TypeError, ValueError):
        return "Unknown"
    return WEATHER_CODES.get(numeric_code, f"Weather code {numeric_code}")


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _forecast_request(
    resolved: dict[str, Any],
    *,
    forecast_days: int,
    include_current: bool = False,
) -> dict[str, Any]:
    daily_variables = ",".join(
        [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "precipitation_sum",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "sunrise",
            "sunset",
        ]
    )
    params: dict[str, Any] = {
        "latitude": resolved["latitude"],
        "longitude": resolved["longitude"],
        "daily": daily_variables,
        "forecast_days": forecast_days,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "auto",
    }

    if include_current:
        params["current"] = ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
                "wind_gusts_10m",
                "is_day",
            ]
        )

    return _get_json(FORECAST_URL, params)


def get_current_weather(location: str) -> dict[str, Any]:
    """
    Fetch and normalize current conditions for a location from Open-Meteo.
    """
    resolved = resolve_location(location)
    payload = _forecast_request(resolved, forecast_days=1, include_current=True)
    current = payload.get("current") or {}

    if not current:
        raise WeatherBrokerError("Open-Meteo returned no current weather data.")

    code = current.get("weather_code")
    return {
        "status": "success",
        "source": "Open-Meteo",
        "location": {
            **resolved,
            "timezone": payload.get("timezone") or resolved.get("timezone"),
        },
        "observed_at": current.get("time"),
        "temperature_f": _num(current.get("temperature_2m")),
        "apparent_temperature_f": _num(current.get("apparent_temperature")),
        "humidity_percent": _num(current.get("relative_humidity_2m")),
        "precipitation_in": _num(current.get("precipitation")),
        "wind_speed_mph": _num(current.get("wind_speed_10m")),
        "wind_gusts_mph": _num(current.get("wind_gusts_10m")),
        "weather_code": code,
        "conditions": weather_code_to_text(code),
        "is_day": bool(current.get("is_day", 1)),
    }


def _daily_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    rows: list[dict[str, Any]] = []

    def at(key: str, index: int, default: Any = None) -> Any:
        values = daily.get(key) or []
        return values[index] if index < len(values) else default

    for i, day in enumerate(dates):
        code = at("weather_code", i)
        rows.append(
            {
                "date": day,
                "conditions": weather_code_to_text(code),
                "weather_code": code,
                "high_f": _num(at("temperature_2m_max", i)),
                "low_f": _num(at("temperature_2m_min", i)),
                "precipitation_probability_percent": _num(
                    at("precipitation_probability_max", i)
                ),
                "precipitation_in": _num(at("precipitation_sum", i)),
                "max_wind_mph": _num(at("wind_speed_10m_max", i)),
                "max_wind_gust_mph": _num(at("wind_gusts_10m_max", i)),
                "sunrise": at("sunrise", i),
                "sunset": at("sunset", i),
            }
        )
    return rows


def get_forecast(location: str, days: int = 5) -> dict[str, Any]:
    """
    Fetch a normalized multi-day forecast.

    Args:
        location: City/place/postal code or "lat,lon".
        days: Number of forecast days, clamped to 1-16.

    Returns:
        Dict containing the resolved location and one forecast record per day.
    """
    try:
        days_int = int(days)
    except (TypeError, ValueError) as exc:
        raise WeatherBrokerError("days must be an integer.") from exc

    days_int = max(1, min(days_int, 16))
    resolved = resolve_location(location)
    payload = _forecast_request(resolved, forecast_days=days_int)
    forecast = _daily_rows(payload)

    if not forecast:
        raise WeatherBrokerError("Open-Meteo returned no forecast data.")

    return {
        "status": "success",
        "source": "Open-Meteo",
        "location": {
            **resolved,
            "timezone": payload.get("timezone") or resolved.get("timezone"),
        },
        "days_requested": days_int,
        "forecast": forecast,
    }


def _resolve_requested_date(
    requested: str,
    forecast_rows: list[dict[str, Any]],
) -> str:
    if not forecast_rows:
        raise WeatherBrokerError("No forecast dates are available.")

    value = (requested or "").strip().lower()
    if not value:
        raise WeatherBrokerError("date is required. Use YYYY-MM-DD, 'today', or 'tomorrow'.")

    if value == "today":
        return str(forecast_rows[0]["date"])
    if value == "tomorrow":
        if len(forecast_rows) < 2:
            raise WeatherBrokerError("Tomorrow is not available in the forecast response.")
        return str(forecast_rows[1]["date"])

    try:
        return Date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise WeatherBrokerError(
            "date must be YYYY-MM-DD, 'today', or 'tomorrow'."
        ) from exc


def _build_recommendation(day: dict[str, Any]) -> dict[str, Any]:
    """
    Apply deterministic recommendation thresholds to one daily forecast.

    Rules:
      - Umbrella if precipitation probability >= 40% OR precipitation >= 0.05 in.
      - Jacket if daily low <= 55 F; warm coat wording if low <= 40 F.
      - Outdoor rating is poor for >=70% precip, >=35 mph gusts, >=100 F high,
        or <=20 F low; fair for moderate rain/wind/temperature thresholds;
        otherwise good.
    """
    precip_probability = _num(day.get("precipitation_probability_percent"))
    precip_inches = _num(day.get("precipitation_in"))
    high_f = _num(day.get("high_f"))
    low_f = _num(day.get("low_f"))
    gust_mph = _num(day.get("max_wind_gust_mph"))

    umbrella = precip_probability >= 40 or precip_inches >= 0.05
    jacket = low_f <= 55

    poor = (
        precip_probability >= 70
        or gust_mph >= 35
        or high_f >= 100
        or low_f <= 20
    )
    fair = (
        precip_probability >= 40
        or gust_mph >= 25
        or high_f >= 90
        or low_f <= 40
    )

    if poor:
        outdoor_rating = "poor"
    elif fair:
        outdoor_rating = "fair"
    else:
        outdoor_rating = "good"

    recommendations: list[str] = []
    reasons: list[str] = []

    if umbrella:
        recommendations.append("Bring an umbrella or rain shell.")
        reasons.append(
            f"Precipitation probability is {precip_probability:.0f}% "
            f"with about {precip_inches:.2f} in forecast."
        )
    else:
        recommendations.append("An umbrella is probably not necessary.")
        reasons.append(f"Precipitation probability is {precip_probability:.0f}%.")

    if low_f <= 40:
        recommendations.append("Bring a warm jacket or coat.")
        reasons.append(f"The forecast low is {low_f:.0f} F.")
    elif jacket:
        recommendations.append("Bring a light jacket.")
        reasons.append(f"The forecast low is {low_f:.0f} F.")
    else:
        recommendations.append("A jacket is not strongly indicated by temperature.")
        reasons.append(f"The forecast low is {low_f:.0f} F.")

    if gust_mph >= 35:
        recommendations.append("Use caution with wind-sensitive outdoor plans.")
        reasons.append(f"Wind gusts may reach {gust_mph:.0f} mph.")

    if high_f >= 100:
        recommendations.append("Limit strenuous outdoor activity during the hottest part of the day.")
        reasons.append(f"The forecast high is {high_f:.0f} F.")

    return {
        "umbrella_needed": umbrella,
        "jacket_recommended": jacket,
        "outdoor_rating": outdoor_rating,
        "recommendations": recommendations,
        "reasoning": reasons,
    }


def get_travel_recommendation(location: str, date: str) -> dict[str, Any]:
    """
    Produce a simple derived travel/outdoor recommendation from forecast data.

    This is intentionally rule-based so the MCP tool demonstrates prediction/
    recommendation logic instead of merely echoing raw weather API values.
    """
    # Request the maximum regular forecast horizon so an ISO date can be found.
    forecast_result = get_forecast(location, days=16)
    rows = forecast_result["forecast"]
    target_date = _resolve_requested_date(date, rows)

    day = next((row for row in rows if row["date"] == target_date), None)
    if day is None:
        available_start = rows[0]["date"]
        available_end = rows[-1]["date"]
        raise WeatherBrokerError(
            f"Date {target_date} is outside the available forecast window "
            f"({available_start} through {available_end})."
        )

    recommendation = _build_recommendation(day)
    return {
        "status": "success",
        "source": "Open-Meteo",
        "location": forecast_result["location"],
        "date": target_date,
        "forecast": day,
        **recommendation,
        "disclaimer": (
            "This is a simple rule-based planning recommendation, not an official "
            "weather warning. Check local authorities for severe-weather guidance."
        ),
    }
