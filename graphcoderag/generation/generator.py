"""
LLM Generator -- Generates answers from retrieved code context using an LLM.

Supports two backends:
1. Anthropic Claude API (cloud, paid, higher quality)
2. Ollama (local, free, requires Ollama installed)

Usage:
    from graphcoderag.generation.generator import LLMGenerator
    gen = LLMGenerator()
    answer = gen.generate(query="How does X work?", context_chunks=results)
"""
from typing import List, Optional
from graphcoderag.generation.prompt_templates import (
    build_prompt, get_system_message, format_context
)
import logging
logger = logging.getLogger(__name__)
from graphcoderag.config import (
    ANTHROPIC_API_KEY, LLM_MODEL,
    USE_LOCAL_LLM, LOCAL_LLM_MODEL,
)


class LLMGenerator:
    """Generates answers using an LLM with retrieved code context."""

    def __init__(
        self,
        use_local: Optional[bool] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize the LLM generator.

        Args:
            use_local: Force local (Ollama) or cloud (Anthropic). Defaults to config.
            model: Override model name. Defaults to config.
        """
        self.use_local = use_local if use_local is not None else USE_LOCAL_LLM

        if self.use_local:
            self.model = model or LOCAL_LLM_MODEL
            self._client = None  # Initialized lazily
        else:
            self.model = model or LLM_MODEL
            self._init_anthropic()

    def _init_anthropic(self):
        """Initialize the Anthropic client."""
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Anthropic client: {e}")

    def generate(
        self,
        query: str,
        context_chunks: list,
        template: str = "qa",
        max_context_chunks: int = 10,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        """
        Generate an answer using the LLM with retrieved context.

        Args:
            query: The developer's question.
            context_chunks: List of RetrievalResult objects from retrieval.
            template: Prompt template type: "qa", "explain", or "debug".
            max_context_chunks: Maximum chunks to include in context.
            max_tokens: Maximum tokens in the response.
            temperature: LLM temperature (lower = more deterministic).

        Returns:
            Generated answer string.
        """
        system_msg = get_system_message()
        user_message = build_prompt(
            query=query,
            context_chunks=context_chunks,
            template=template,
            max_context_chunks=max_context_chunks,
        )

        return self._call_llm(system_msg, user_message, max_tokens, temperature)

    def generate_raw(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.0,
    ) -> str:
        """
        Generate a response from a raw prompt string (no context formatting).
        Used by LLM Judge and other tools that build their own prompts.

        Args:
            prompt: The full prompt string.
            max_tokens: Maximum tokens in the response.
            temperature: LLM temperature.

        Returns:
            Generated response string.
        """
        return self._call_llm(
            system_message="You are a helpful assistant.",
            user_message=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def _call_llm(
        self,
        system_message: str,
        user_message: str,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        """Unified LLM call — same message structure for both backends."""
        if self.use_local:
            return self._call_ollama(system_message, user_message, max_tokens, temperature)
        else:
            return self._call_anthropic(system_message, user_message, max_tokens, temperature)

    def _call_anthropic(
        self, system_message, user_message, max_tokens, temperature,
    ) -> str:
        """Call Anthropic Claude API with retry and model fallback."""
        import time

        for attempt in range(3):
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_message,
                    messages=[
                        {"role": "user", "content": user_message}
                    ],
                )
                return response.content[0].text
            except Exception as e:
                error_str = str(e).lower()
                # Retry on overloaded (529), rate limit (429), or transient errors
                is_retryable = any(hint in error_str for hint in [
                    "529", "overloaded", "429", "rate_limit", "rate limit",
                    "503", "service unavailable",
                ])
                if is_retryable:
                    wait = 2 ** attempt
                    logger.warning(f"Anthropic {self.model} retry {attempt+1}/3 (wait {wait}s): {e}")
                    if attempt < 2:
                        time.sleep(wait)
                        continue
                else:
                    return f"[LLM Error] Failed to generate response: {e}"

        return f"[LLM Error] {self.model} is currently overloaded after 3 retries. Please try again."

    def _call_ollama(
        self, system_message, user_message, max_tokens, temperature,
    ) -> str:
        """Call Ollama local LLM — same system+user message structure as Anthropic."""
        # Combine system + user into a single prompt for Ollama
        prompt = f"{system_message}\n\n{user_message}"

        try:
            import requests
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.ConnectionError:
            return (
                "[LLM Error] Cannot connect to Ollama. "
                "Make sure Ollama is running: `ollama serve`"
            )
        except Exception as e:
            return f"[LLM Error] Ollama generation failed: {e}"

    def test_connection(self) -> bool:
        """Test if the LLM backend is reachable."""
        try:
            if self.use_local:
                import requests
                resp = requests.get("http://localhost:11434/api/tags", timeout=5)
                return resp.status_code == 200
            else:
                # Anthropic: just verify the client exists
                return self._client is not None
        except Exception:
            return False
