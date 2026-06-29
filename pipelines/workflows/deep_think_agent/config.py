"""Configuration management for Gemma 4 Multi-Agent Deep Think."""

import os

from dotenv import load_dotenv


# Proactively load environment variables from file
load_dotenv()


# Standard exports
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://searxng:8080")
