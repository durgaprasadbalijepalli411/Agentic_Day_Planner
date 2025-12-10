from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from crewai import Agent, Crew, LLM, Task

from tools import get_city_news, get_local_spots, get_weather_outlook
from dotenv import load_dotenv

load_dotenv()

os.environ["CREWAI_TRACING_ENABLED"] = "false"


API_KEY = "AIzaSyB1amnaa8-pLFW1WMumnp9pxh1W7M6y770"
CLAUDE_API_KEY="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"


def build_llm() -> LLM:
    return LLM(model="gemini/gemini-2.0-flash", api_key=API_KEY)

# def build_llm() -> LLM:
#     """Build LLM with Claude using environment variable"""
#     return LLM(
#         # LiteLLM format for Claude
#         model="anthropic/claude-3-haiku-20240307",
        
#         # No need to pass api_key if using environment variable
#         temperature=0.7,
#         max_tokens=4000,
        
#         # Optional: Specify provider explicitly
#         provider="anthropic"
#     )


def _format_user_context(user_data: Dict[str, str]) -> str:
    return "\n".join(f"{key.title()}: {value or 'N/A'}" for key, value in user_data.items())


def _stringify_output(result: Any) -> str:
    if hasattr(result, "raw_output"):
        result = result.raw_output
    elif hasattr(result, "output"):
        result = result.output
    if not isinstance(result, str):
        result = str(result)
    return result


def _run_single_task(agent: Agent, description: str, expected_output: str) -> str:
    task = Task(
        description=description,
        expected_output=expected_output,
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], verbose=True, tracing=False)
    result = crew.kickoff()
    return _stringify_output(result)


def _notify(progress: Optional[Callable[[str, str], None]], stage: str, message: str) -> None:
    if progress:
        progress(stage, message)


def plan_day_workflow(
    user_data: Dict[str, str],
    plan_date: str,
    commitments: str | None = None,
    adjustments: str | None = None,
    progress: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    if not user_data.get("location"):
        raise ValueError("Location is required to generate the day plan.")
    if not plan_date:
        raise ValueError("Plan date is required.")

    llm = build_llm()

    # 1. Profile Data Collector Agent
    profile_agent = Agent(
        role="User Data Curator",
        goal="Transform raw onboarding answers into a structured persona profile.",
        backstory="You are a thoughtful researcher who captures user context crisply for planners.",
        llm=llm,
        verbose=True,
    )
    # 2. Weather Data Collector Agent
    weather_agent = Agent(
        role="Climate Analyst",
        goal="Gather actionable weather intelligence for schedule planning.",
        backstory="You specialize in translating forecasts into human-friendly takeaways.",
        tools=[get_weather_outlook],
        llm=llm,
        verbose=True,
    )
    # 3. Local Insights Data Collector Agent
    insights_agent = Agent(
        role="City Culture Scout",
        goal="Discover concrete venues, events, and indoor-safe options for the user's city today.",
        backstory="A plugged-in local guide who cross-references news and maps to surface specific recommendations.",
        tools=[get_city_news, get_local_spots],
        llm=llm,
        verbose=True,
    )
    # 4. Planning Agent
    planning_agent = Agent(
        role="Personal Day Planner",
        goal="Design a balanced, climate-aware day plan tuned to the user's lifestyle.",
        backstory="Seasoned lifestyle coach blending productivity, wellness, and leisure.",
        llm=llm,
        verbose=True,
    )

    # 2. Execute Steps
    user_context = _format_user_context(user_data)

    # Step 1: Persona
    _notify(progress, "persona", "Summarizing your vibe for this day off...")
    profile_description = (
        "Create a JSON persona profile for a leisure day planner. "
        "The user is completely off work on the specified date, so focus on lifestyle cues.\n"
        f"Plan date: {plan_date}\n"
        f"{user_context}\n"
        "Return keys: name, email, location, profession, hobbies, interests, priorities, "
        "tone, ideal_pace, summary."
    )
    profile = _run_single_task(
        profile_agent,
        profile_description,
        expected_output="Valid JSON document capturing the requested keys with concise values.",
    )

    # Step 2: Weather
    _notify(progress, "weather", "Checking the weather and comfort levels for the day...")
    weather_description = (
        "Retrieve the weather outlook for the selected leisure date using GetWeatherOutlook. "
        "You must call the tool with both location and target_date in ISO format.\n"
        f"Location: {user_data['location']}\n"
        f"Date: {plan_date}"
    )
    weather = _run_single_task(
        weather_agent,
        weather_description,
        expected_output="3-5 bullet insights that mention temperature, precipitation, daylight, and comfort tips.",
    )

    # Step 3: Local Insights
    _notify(progress, "insights", "Hunting for venues and happenings in your city you'll love...")
    insights_description = (
        "Surface concrete happenings and venues for the user's free day. "
        "Use GetCityNews with location, target_date, and interest keywords to find relevant events. "
        "Use GetLocalSpots to gather nearby venues for the stated hobbies/interests. "
        "Tag each suggestion as Outdoor or Indoor-safe.\n"
        f"Location: {user_data['location']}\n"
        f"Date: {plan_date}\n"
        f"Hobbies: {user_data.get('hobbies') or 'N/A'}\n"
        f"Interests: {user_data.get('interests') or 'N/A'}"
    )
    local_insights = _run_single_task(
        insights_agent,
        insights_description,
        expected_output=(
            "Return markdown with sections Events/Matches, Indoor Picks, Outdoor Picks. "
            "List specific names with short reasons (e.g., 'Attend Hyderabad Hunters match at Gachibowli Indoor Stadium')."
        ),
    )

    # Step 4: Final Plan
    _notify(progress, "planning", "Crafting your curated timeline(Final Step)...")
    planning_description = (
        "Design a detailed leisure-day itinerary (no work items) for the specified date.\n"
        f"Date: {plan_date}\n"
        f"Persona JSON:\n{profile}\n"
        f"Weather insights:\n{weather}\n"
        f"Local picks:\n{local_insights}\n"
        f"Fixed commitments (must appear exactly at given times): {commitments or 'None provided'}\n"
        f"User adjustments or feedback: {adjustments or 'No additional preferences supplied'}\n"
        "Output should cover Morning, Midday, Afternoon, Evening, and Late Night. "
        "Each block must specify concrete times and explicit venues or neighborhoods. "
        "Reference at least two suggestions from the local picks, and adjust indoor/outdoor balance based on the weather. "
        "Respect fixed commitments even if it requires reshuffling nearby blocks. "
        "Assume the user is free the entire day and prefers a balanced pace."
    )
    plan = _run_single_task(
        planning_agent,
        planning_description,
        expected_output=(
            "Return markdown with headings: Morning, Midday, Afternoon, Evening, Late Night. "
            "Under each heading provide bullet timelines (e.g., '08:00-09:30 – Breakfast at ...'). "
            "Do not add extra sections such as Productivity or Wellness."
        ),
    )

    return {
        "persona": profile,
        "weather": weather,
        "local_insights": local_insights,
        "plan": plan,
        "date": plan_date,
        "commitments": commitments or "",
        "adjustments": adjustments or "",
    }
