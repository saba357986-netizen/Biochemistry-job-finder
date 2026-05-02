"""
llm_engine.py - Free LLM interface
Supports: Ollama (local), Groq (free API), Together AI (free credits)

FIX: test_llm now shows the correct model name for the active backend,
not always OLLAMA_MODEL regardless of which backend is configured.
"""
import requests
import json
import logging
from config import (LLM_BACKEND, OLLAMA_MODEL, OLLAMA_URL,
                    GROQ_API_KEY, GROQ_MODEL,
                    TOGETHER_API_KEY, TOGETHER_MODEL)

log = logging.getLogger(__name__)


def call_ollama(prompt: str, system: str = "", max_tokens=1500) -> str:
    """Call local Ollama instance (completely free, runs on your machine)."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{system}\n\n{prompt}" if system else prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.7}
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        log.error("Ollama not running. Start it with: ollama serve")
        return ""
    except Exception as e:
        log.error(f"Ollama error: {e}")
        return ""


def call_groq(prompt: str, system: str = "", max_tokens=1500) -> str:
    """Call Groq API (free tier: 14,400 req/day, very fast)."""
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        log.error("Groq API key not set. Edit config.py → GROQ_API_KEY")
        return ""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=30
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.error(f"Groq error: {e}")
        return ""


def call_together(prompt: str, system: str = "", max_tokens=1500) -> str:
    """Call Together AI (free credits on signup)."""
    if not TOGETHER_API_KEY or TOGETHER_API_KEY == "your_together_api_key_here":
        log.error("Together AI key not set. Edit config.py → TOGETHER_API_KEY")
        return ""
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": TOGETHER_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    try:
        resp = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers=headers, json=payload, timeout=60
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.error(f"Together AI error: {e}")
        return ""


def ask_llm(prompt: str, system: str = "", max_tokens=1500) -> str:
    """
    Main LLM interface — uses configured backend with automatic fallback.
    Falls back through: configured backend → next available backend.
    """
    if LLM_BACKEND == "ollama":
        result = call_ollama(prompt, system, max_tokens)
        if result:
            return result
        log.warning("Ollama failed, trying Groq as fallback...")
        return call_groq(prompt, system, max_tokens)

    elif LLM_BACKEND == "groq":
        result = call_groq(prompt, system, max_tokens)
        if result:
            return result
        log.warning("Groq failed, trying Ollama as fallback...")
        return call_ollama(prompt, system, max_tokens)

    elif LLM_BACKEND == "together":
        result = call_together(prompt, system, max_tokens)
        if result:
            return result
        log.warning("Together AI failed, trying Groq as fallback...")
        return call_groq(prompt, system, max_tokens)

    log.error("All LLM backends failed.")
    return ""


def get_active_model_name() -> str:
    """
    FIX: Returns the correct model name for whichever backend is active.
    Previously, main.py always showed OLLAMA_MODEL even when using Groq.
    """
    if LLM_BACKEND == "ollama":
        return OLLAMA_MODEL
    elif LLM_BACKEND == "groq":
        return GROQ_MODEL
    elif LLM_BACKEND == "together":
        return TOGETHER_MODEL
    return "unknown"


def extract_json(text: str) -> dict:
    """Safely extract JSON from LLM response."""
    import re
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    try:
        return json.loads(text.strip())
    except Exception:
        return {}
