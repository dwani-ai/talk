import os
import sys
import logging

sys.path.append("..")
from dotenv import load_dotenv

from google.adk import Agent
from google.genai import types
from typing import Optional, List, Dict

from google.adk.tools.tool_context import ToolContext

# NEW: import the Client class (note the package root)
from google import genai

load_dotenv()


import os
from google.adk.models.lite_llm import LiteLlm

# ADK's LiteLLM wrapper reads specific env vars, but explicit config is safer for local models
MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),          # ← changed from model_name
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


# Tools (add the tool here when instructed)
def save_attractions_to_state(
tool_context: ToolContext,
attractions: List[str]
) -> dict[str, str]:
    """Saves the list of attractions to state["attractions"].

    Args:
        attractions [str]: a list of strings to add to the list of attractions

    Returns:
        None
    """
    # Load existing attractions from state. If none exist, start an empty list
    existing_attractions = tool_context.state.get("attractions", [])

    # Update the 'attractions' key with a combo of old and new lists.
    # When the tool is run, ADK will create an event and make
    # corresponding updates in the session's state.
    tool_context.state["attractions"] = existing_attractions + attractions

    # A best practice for tools is to return a status message in a return dict
    return {"status": "success"}



# Agents

attractions_planner = Agent(
    name="attractions_planner",
    model=MODEL,
    description="Build a list of attractions to visit in a country.",
    instruction="""
        - Provide the user options for attractions to visit within their selected country.
        - When they reply, use your tool to save their selected attraction and then provide more possible attractions.
        - If they ask to view the list, provide a bulleted list of { attractions? } and then suggest some more.

        """,
    tools=[save_attractions_to_state]

)

travel_brainstormer = Agent(
    name="travel_brainstormer",
    model=MODEL,
    description="Help a user decide what country to visit.",
    instruction="""
        Provide a few suggestions of popular countries for travelers.

        Help a user identify their primary goals of travel:
        adventure, leisure, learning, shopping, or viewing art

        Identify countries that would make great destinations
        based on their priorities.
        """,
)

root_agent = Agent(
    name="steering",
    model=MODEL,
    description="Start a user on a travel adventure.",
    instruction="""
        Ask the user if they know where they'd like to travel
        or if they need some help deciding.

        - If the user does NOT know where to go and wants ideas,
          delegate to the `travel_brainstormer` sub-agent.

        - If the user ALREADY has a country in mind,
          delegate to the `attractions_planner` sub-agent
          to list attractions in that country.

        - If they need help deciding, send them to 'travel_brainstormer'.
        
        - If they know what country they'd like to visit, send them to the 'attractions_planner'.

        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    sub_agents=[travel_brainstormer, attractions_planner],
)
