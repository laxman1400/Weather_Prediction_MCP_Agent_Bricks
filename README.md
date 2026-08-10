# Weather Prediction MCP Server + Agent Bricks

A Databricks Day-3 style project that replaces the Alpaca paper-trading backend with a weather MCP server.

The project uses **FastMCP** for tool exposure, **Open-Meteo** for live weather data, and a **Databricks Agent Bricks agent** as the natural-language client.

## Architecture

```text
User
  |
  v
Databricks Agent Bricks
  |
  | MCP tool calls
  v
mcp_server/weather_mcp_server.py
  |
  | thin adapter calls
  v
mcp_server/weather_broker.py
  |
  | HTTPS / JSON
  v
Open-Meteo Geocoding + Forecast APIs
```

The MCP server is deployed as its own Databricks App. The agent is configured separately in Agent Bricks and connects to the app as an external MCP service.

## Why Open-Meteo?

Open-Meteo was selected because:

- no API key is required for the free/non-commercial API
- no signup or credit card is required
- it supports worldwide geocoding and forecasts
- it provides current conditions, daily forecasts, precipitation probability, weather codes, humidity and wind
- it lets the assignment focus on MCP/agent design instead of secret management

This project uses Open-Meteo's free/non-commercial endpoints. Follow Open-Meteo's current usage/licensing requirements, including attribution requirements where applicable.

## Repository structure

```text
weather-prediction-mcp-agent/
├── mcp_server/
│   ├── weather_broker.py
│   ├── weather_mcp_server.py
│   ├── requirements.txt
│   └── app.yaml
├── agent/
│   ├── SYSTEM_PROMPT.md
│   ├── TOOL_LIST.md
│   ├── DEMO_PROMPTS.md
│   └── agent_config.json
├── screenshots/
│   └── README.md
├── README.md
└── .gitignore
```

## MCP tools

### `get_current_weather(location)`

Returns current:

- temperature
- apparent temperature
- humidity
- precipitation
- wind speed/gusts
- weather condition

Example:

```text
What's the weather in Chicago right now?
```

### `get_forecast(location, days=5)`

Returns a 1-16 day forecast with:

- daily high/low
- precipitation probability
- precipitation amount
- condition
- wind/gusts
- sunrise/sunset

Example:

```text
Will it rain in Chicago tomorrow?
```

### `get_travel_recommendation(location, date)`

A derived recommendation tool rather than a raw API passthrough.

Rules include:

- umbrella if precipitation probability is at least 40%, or forecast precipitation is at least 0.05 inches
- jacket if the daily low is 55 F or below
- `poor` outdoor rating for high rain risk, strong gusts, extreme heat, or extreme cold
- otherwise `fair` or `good` based on moderate thresholds

Example:

```text
Should I bring a jacket to Austin tomorrow?
```

### `health()`

Diagnostic tool that confirms the MCP server is running.

## Separation of responsibilities

`weather_mcp_server.py` contains:

- `FastMCP`
- `@mcp.tool` definitions
- tool docstrings
- clean tool-level error responses
- Databricks App HTTP startup

`weather_broker.py` contains:

- all `requests` HTTP calls
- Open-Meteo geocoding
- location resolution
- Open-Meteo forecast/current calls
- JSON parsing and normalization
- WMO weather-code mapping
- recommendation thresholds

There are **no raw weather API HTTP calls inside the `@mcp.tool` functions**.

## Authentication and secrets

Open-Meteo does not require an API key for this project's free/non-commercial usage, so:

- there is no weather API secret to configure
- no API key is hardcoded
- no credential should be committed to Git

If you later replace Open-Meteo with a provider that requires a key, store it as a Databricks secret and read it at runtime.

## Run locally

From the repository root:

```bash
cd mcp_server
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python weather_mcp_server.py
```

FastMCP starts the server on port `8000` locally unless `PORT` is set.

## Deploy the MCP server as a Databricks App

1. Push this repository to your GitHub account.
2. Create a Databricks Git folder connected to the repository.
3. In Databricks, go to **Compute > Apps > Create app**.
4. Create a custom MCP app. A name such as `mcp-weather-prediction` is recommended.
5. Point the app source to the repository's **`mcp_server/` subfolder** so Databricks sees that folder's `app.yaml`.
6. Deploy.
7. Wait for the deployment status to become active/running.
8. Copy the Databricks App URL.

The MCP server uses FastMCP HTTP transport and listens on the `DATABRICKS_APP_PORT` environment variable provided by Databricks Apps.

## Register as an external MCP

The exact UI wording can vary by workspace.

1. Go to **AI Gateway > MCPs**.
2. Choose **Register MCP Server / Add MCP**.
3. Configure the deployed Databricks App URL as the MCP endpoint/connection.
4. Give the MCP service a name such as `weather-prediction`.
5. Expose:
   - `get_current_weather`
   - `get_forecast`
   - `get_travel_recommendation`
   - optionally `health`
6. Grant the agent permission to execute the MCP service if prompted.

## Build the Agent Bricks agent

1. Go to **Agents > Agent Bricks > Create agent**.
2. Create a Custom LLM/tool-calling agent.
3. Add the registered weather MCP service under **Tools**.
4. Copy the contents of [`agent/SYSTEM_PROMPT.md`](agent/SYSTEM_PROMPT.md) into the agent's system prompt.
5. Save/deploy the agent.
6. Verify that tool calls are visible and successful.

The tool descriptions are in [`agent/TOOL_LIST.md`](agent/TOOL_LIST.md).

## Required demonstration

Test at least three natural-language questions and capture screenshots:

1. `What's the weather in Chicago right now?`
2. `Will it rain in Chicago tomorrow?`
3. `Should I bring a jacket to Austin tomorrow?`

See [`agent/DEMO_PROMPTS.md`](agent/DEMO_PROMPTS.md).

Place final screenshots under `screenshots/`.

## Error handling

The adapter raises clean weather-specific exceptions for:

- unresolved locations
- invalid coordinates
- invalid dates
- API/network failures
- malformed responses

The MCP layer converts expected failures into JSON such as:

```json
{
  "status": "error",
  "error_type": "LocationNotFoundError",
  "message": "Could not resolve location ..."
}
```

The system prompt instructs the agent to clarify or report the failure rather than hallucinating weather data.

## Known limitations

- The recommendation rules are intentionally simple thresholds, not a trained ML weather model.
- Forecasts are probabilistic and can change as weather models update.
- The project uses Fahrenheit, mph and inches for a simple consistent demo.
- The server does not expose official severe-weather alerts.
- Location geocoding chooses the best candidate and can still be ambiguous for places with duplicate names.
- `get_travel_recommendation` is limited to Open-Meteo's available forecast window.

## Improvements with more time

- add NWS severe-weather alerts as a second MCP tool/source for U.S. locations
- add user-selectable metric/imperial units
- add historical-weather comparison
- add a `compare_weather` tool for several cities
- persist recent agent queries/predictions in Lakebase
- build the optional dashboard Databricks App
- evaluate the recommendation thresholds against historical outcomes

## Submission checklist

Before submitting:

- [ ] GitHub repo contains `mcp_server/` and `agent/`
- [ ] MCP Databricks App is deployed
- [ ] external MCP service is registered
- [ ] Agent Bricks agent has all required weather tools
- [ ] system prompt is saved in the repo and Agent Bricks
- [ ] all three demo prompts work
- [ ] three screenshots are committed under `screenshots/`
- [ ] README is complete
- [ ] no secrets or tokens are committed
- [ ] submission includes GitHub repo link
- [ ] submission includes Databricks App URL, or screenshots if workspace access cannot be shared

## Data source

Weather and geocoding data: **Open-Meteo**.

## github repo url
https://github.com/laxman1400/Weather_Prediction_MCP_Agent_Bricks

## MCP app url
https://mcp-weather-prediction-7474658703647632.aws.databricksapps.com
