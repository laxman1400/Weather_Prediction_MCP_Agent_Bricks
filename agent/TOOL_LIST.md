# Agent Tool List

Register the deployed Weather Prediction MCP server with Databricks and expose these tools to the Agent Bricks agent.

## 1. `get_current_weather`

**Purpose:** Current conditions.

**Arguments**
- `location` — city/place/postal code (for example `Chicago, IL`) or `lat,lon`.

**Returns**
- temperature and apparent temperature (F)
- humidity (%)
- precipitation (in)
- wind speed/gusts (mph)
- WMO/Open-Meteo condition text
- resolved location and observation time

**Example user question:**  
`What's the weather in Chicago right now?`

---

## 2. `get_forecast`

**Purpose:** Future/multi-day forecast.

**Arguments**
- `location`
- `days` — 1 through 16

**Returns per day**
- high/low temperature (F)
- precipitation probability (%)
- precipitation amount (in)
- condition
- wind/gusts
- sunrise/sunset

**Example user question:**  
`Will it rain in Chicago tomorrow?`

---

## 3. `get_travel_recommendation`

**Purpose:** Derived weather recommendation rather than raw API passthrough.

**Arguments**
- `location`
- `date` — `today`, `tomorrow`, or `YYYY-MM-DD`

**Rules**
- umbrella: precipitation probability >= 40% OR forecast precipitation >= 0.05 in
- jacket: daily low <= 55 F
- outdoor rating becomes `poor` for strong rain/wind or temperature extremes
- otherwise the rating is `fair` or `good` based on deterministic thresholds

**Returns**
- `umbrella_needed`
- `jacket_recommended`
- `outdoor_rating`
- recommendation text
- explicit reasoning
- underlying forecast values

**Example user question:**  
`Should I bring a jacket to Austin tomorrow?`

---

## 4. `health`

Diagnostic tool for confirming that the MCP server is running. It is not needed for normal weather answers.
