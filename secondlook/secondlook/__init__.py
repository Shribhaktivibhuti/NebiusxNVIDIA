"""Vibe Bro: checks AI-written Python and teaches freshers to spot its bugs."""

from pathlib import Path

from dotenv import load_dotenv

# Locally, read the API keys from secondlook/.env. Keys already set (for example from
# Streamlit secrets or `source .env`) are left alone.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
