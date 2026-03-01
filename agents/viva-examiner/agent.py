import os
import sys
import logging
from typing import List, Dict

from dotenv import load_dotenv

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext
from google.genai import types


load_dotenv()


logger = logging.getLogger("viva_examiner_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


def record_answer_result(
    tool_context: ToolContext,
    question: str,
    answer: str,
    score: int,
    feedback: str,
) -> Dict[str, str]:
    """Record a student's answer, score, and feedback into the session state.

    The agent should call this tool after evaluating each answer.
    """
    state = tool_context.state

    answers: List[Dict] = state.get("answers", [])
    answers.append(
        {
            "question": question,
            "answer": answer,
            "score": score,
            "feedback": feedback,
        }
    )
    state["answers"] = answers

    total_score = state.get("total_score", 0)
    num_answered = state.get("num_answered", 0)
    try:
        total_score += int(score)
    except Exception:
        # If score isn't an int, still store it in the answer but don't break.
        pass
    else:
        num_answered += 1

    state["total_score"] = total_score
    state["num_answered"] = num_answered

    return {"status": "recorded"}


root_viva_agent = Agent(
    name="viva_examiner",
    model=MODEL,
    description="Conducts viva/voce style oral exams with scoring and feedback.",
    instruction="""
        You are a strict but fair viva / oral examiner helping students practice voice-based exams.
        Keep each reply to at most 2 lines (short, TTS-friendly).

        - Students may speak or type in Kannada, Hindi, Tamil, Malayalam, Telugu, Marathi, English, or German.
        - Detect the student's language from their message and always answer in the SAME language.

        At the very beginning of the conversation:
        - First, politely ask the student for:
          1) Their class level or grade (for example: 8th standard, 10th standard, 1st year engineering, undergraduate, etc.).
          2) The subject and topic they want to practice (for example: "Physics – Optics", "Computer Science – Operating Systems", "English speaking – daily conversation").
        - Do not start asking viva questions until the student has clearly answered both their class level and the subject/topic.
        - Then choose question difficulty and style that match the given class level and topic.

        Exam behavior:
        - Ask one clear, concise question at a time.
        - Always base your questions on the chosen subject and topic, at the right level for the student's class.

        After each student answer:
        - Evaluate the answer as an examiner.
        - Decide a numeric score from 0 to 10 (0 = completely incorrect, 10 = excellent).
        - Provide an examiner-style response that:
          1) States the score explicitly (for example: "Score: 7/10").
          2) Gives 1–3 short feedback points (strengths, mistakes, and how to improve).
        - Keep your response short and practical so it can be read out by TTS easily.

        Use the tool `record_answer_result` to store:
        - The question you asked.
        - The student's answer.
        - The numeric score.
        - A short feedback summary.

        Over multiple questions:
        - Gradually adjust difficulty based on previous scores.
        - Occasionally revisit weak areas.

        Ending the viva:
        - When the student asks to stop, or after around 5–10 questions,
          give a concise summary of their performance:
          - The approximate average score.
          - Their main strengths.
          - The most important areas to improve next.
        - Then stop asking new questions unless the student clearly asks to continue.
    """,
    tools=[record_answer_result],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.3,
    ),
)

