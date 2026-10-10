"""The one model for every agent: gpt-6 luna, OpenAI through Portkey (see AGENTS.md)."""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

HW_DIR = Path(__file__).resolve().parent.parent
load_dotenv(HW_DIR / ".env")
load_dotenv(HW_DIR.parent.parent / ".env")  # the repo-root .env holds PORTKEY_API_KEY

MODEL_NAME = os.getenv("PORTKEY_MODEL", "gpt-6 luna")


def make_model() -> OpenAIChatModel:
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to the repo-root .env or hw5/.env.")
    return OpenAIChatModel(
        MODEL_NAME,
        provider=OpenAIProvider(
            openai_client=AsyncOpenAI(
                base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1"),
                api_key=api_key,
                default_headers={"x-portkey-api-key": api_key, "x-portkey-provider": "openai"},
            )
        ),
    )
