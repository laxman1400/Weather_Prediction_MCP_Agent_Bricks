# Required Demonstration

After the MCP server is deployed and attached to Agent Bricks, capture screenshots for at least these three prompts.

## Demo 1 — Current conditions

**Prompt**

> What's the weather in Chicago right now?

**Expected tool**

`get_current_weather`

**Screenshot should show**
- the natural-language question
- the tool call/tool trace if Agent Bricks exposes it
- the final answer

---

## Demo 2 — Forecast

**Prompt**

> Will it rain in Chicago tomorrow?

**Expected tool**

`get_forecast`

**Screenshot should show**
- forecast tool use
- precipitation evidence
- final natural-language answer

---

## Demo 3 — Recommendation

**Prompt**

> Should I bring a jacket to Austin tomorrow?

**Expected tool**

`get_travel_recommendation`

**Screenshot should show**
- recommendation tool use
- forecast evidence/threshold reasoning
- final recommendation

Save the screenshots in the repo's `screenshots/` folder before submission.
