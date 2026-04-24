"""
LLM Judge — Cross-model evaluation using Gemini 2.5 Flash.

Eliminates self-bias by using a different provider (Google) than the generator (Qwen/Ollama).
Implements the evaluation guide's 5-level rubric with verbosity bias mitigation.

Modes:
  - Independent scoring: Rate each answer on accuracy/completeness/helpfulness (1-5)
  - Pairwise preference: "Which answer is more helpful?" with position-swap debiasing

Usage:
    from graphcoderag.evaluation.llm_judge import GeminiJudge
    judge = GeminiJudge()
    scores = judge.rate_answer(question, answer, ground_truth_files)
    pref = judge.pairwise_compare(question, answer_a, answer_b, ground_truth_files)
"""
import json
import os
import time
from typing import Dict, Optional, List
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────
#  Scoring Rubric (per Evaluation Guide §3.2)
# ─────────────────────────────────────────────────────────

JUDGE_PROMPT = """You are an expert code reviewer evaluating the quality of a code assistant's answer to a GitHub issue.

## GitHub Issue (Question)
{question}

## Ground Truth (Files that needed to change)
{ground_truth}

## Answer Being Evaluated
{answer}

## Scoring Rubric

Rate the answer on three dimensions using this EXACT 1-5 scale:

### Accuracy (1-5)
1: Answer identifies completely wrong files and functions; no relevant code mentioned.
2: Mentions some relevant code but misses the core issue; partially correct direction.
3: Identifies the right area of the codebase but explanation is incomplete or surface-level.
4: Correctly identifies the root cause and most relevant files/functions; minor gaps only.
5: Pinpoints the exact files, functions, and logic that need to change; matches ground truth.

### Completeness (1-5)
1: Misses all relevant files and functions that need to change.
2: Mentions 1 relevant file but misses others; incomplete picture.
3: Covers the main file but misses important related files or dependencies.
4: Mentions most relevant files and explains the connections; minor omissions.
5: Comprehensive — identifies all files, functions, and their relationships.

### Helpfulness (1-5)
1: Not useful — too vague, confusing, or misleading for a developer.
2: Slightly useful — gives a general direction but lacks actionable detail.
3: Moderately useful — developer gets the idea but needs significant additional investigation.
4: Very useful — developer can start fixing the bug with this guidance; specific references.
5: Extremely useful — developer has a clear action plan with exact locations and reasoning.

IMPORTANT: Length should NOT influence your scoring. A short, precise answer that identifies the correct root cause should score HIGHER than a long, verbose answer that includes irrelevant information.

Respond with ONLY a JSON object in this exact format:
{{"accuracy": <1-5>, "completeness": <1-5>, "helpfulness": <1-5>, "reasoning": "<brief explanation of your scores>"}}"""


PAIRWISE_PROMPT = """You are an expert code reviewer comparing two answers to the same GitHub issue.

## GitHub Issue
{question}

## Ground Truth (Files that needed to change)
{ground_truth}

## Answer A
{answer_a}

## Answer B
{answer_b}

## Task
Which answer would be MORE HELPFUL to a developer trying to fix this bug?

Consider:
- Does it correctly identify the files and functions that need to change?
- Does it explain the root cause accurately?
- Is it actionable — can the developer start working from this?

IMPORTANT: Length should NOT influence your judgment. A concise, precise answer is better than a verbose one with irrelevant details.

Respond with ONLY a JSON object:
{{"winner": "A" or "B" or "tie", "reasoning": "<brief explanation>"}}"""


class GeminiJudge:
    """Cross-model judge using Gemini 2.5 Flash for unbiased evaluation."""

    def __init__(self, api_key: str = None, model: str = None):
        import google.generativeai as genai

        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model or os.getenv("JUDGE_MODEL", "gemini-2.5-flash")

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set. Get one free at aistudio.google.com")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)
        self._call_count = 0

    def rate_answer(
        self,
        question: str,
        answer: str,
        ground_truth_files: List[str] = None,
        ground_truth_diff: str = "",
    ) -> Dict[str, float]:
        """
        Rate an answer using Gemini as judge.

        Args:
            question: The original GitHub issue / question.
            answer: The generated answer to evaluate.
            ground_truth_files: List of files that the fix actually touched.
            ground_truth_diff: Optional patch diff for the ground truth.

        Returns:
            Dict with accuracy, completeness, helpfulness (1-5), avg_score, reasoning.
        """
        gt = ""
        if ground_truth_files:
            gt = "Files modified in the fix:\n" + "\n".join(f"  - {f}" for f in ground_truth_files)
        if ground_truth_diff:
            gt += f"\n\nPatch diff:\n{ground_truth_diff[:1000]}"
        if not gt:
            gt = "(No ground truth provided)"

        prompt = JUDGE_PROMPT.format(
            question=question[:1500],
            ground_truth=gt,
            answer=answer[:2000],
        )

        raw = self._call_gemini(prompt)
        return self._parse_scores(raw)

    def pairwise_compare(
        self,
        question: str,
        answer_a: str,
        answer_b: str,
        ground_truth_files: List[str] = None,
        debias: bool = True,
    ) -> Dict[str, str]:
        """
        Pairwise preference: which answer is more helpful?

        With debias=True, runs twice with positions swapped and reports
        the consensus (eliminates position bias).

        Returns:
            Dict with 'winner' ('A', 'B', or 'tie'), 'reasoning', and
            if debiased: 'run1_winner', 'run2_winner'.
        """
        gt = ""
        if ground_truth_files:
            gt = "Files modified:\n" + "\n".join(f"  - {f}" for f in ground_truth_files)

        # Run 1: A first, B second
        prompt1 = PAIRWISE_PROMPT.format(
            question=question[:1500],
            ground_truth=gt or "(No ground truth)",
            answer_a=answer_a[:2000],
            answer_b=answer_b[:2000],
        )
        raw1 = self._call_gemini(prompt1)
        result1 = self._parse_pairwise(raw1)

        if not debias:
            return result1

        # Run 2: B first, A second (position swap)
        prompt2 = PAIRWISE_PROMPT.format(
            question=question[:1500],
            ground_truth=gt or "(No ground truth)",
            answer_a=answer_b[:2000],  # B is now "A"
            answer_b=answer_a[:2000],  # A is now "B"
        )
        raw2 = self._call_gemini(prompt2)
        result2 = self._parse_pairwise(raw2)

        # Reconcile: swap result2's winner back
        r2_winner = result2.get("winner", "tie")
        if r2_winner == "A":
            r2_winner_normalized = "B"  # "A" in swapped = original B
        elif r2_winner == "B":
            r2_winner_normalized = "A"  # "B" in swapped = original A
        else:
            r2_winner_normalized = "tie"

        r1_winner = result1.get("winner", "tie")

        # Consensus
        if r1_winner == r2_winner_normalized:
            final = r1_winner
        else:
            final = "tie"  # Disagreement = tie

        return {
            "winner": final,
            "run1_winner": r1_winner,
            "run2_winner": r2_winner_normalized,
            "reasoning": result1.get("reasoning", ""),
        }

    def _call_gemini(self, prompt: str, max_retries: int = 5) -> str:
        """Call Gemini API with retries and rate-limit backoff."""
        for attempt in range(max_retries):
            try:
                self._call_count += 1
                response = self.model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.0,
                        "max_output_tokens": 1024,
                        "response_mime_type": "application/json",
                    }
                )
                # Pace calls to stay under rate limit
                time.sleep(15)
                return response.text
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower() or "resource" in str(e).lower():
                    wait = 30 * (attempt + 1)
                    print(f"  [Judge] Rate limited, waiting {wait}s...", flush=True)
                    time.sleep(wait)
                elif attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    return f"[Gemini Error] {e}"
        return "[Gemini Error] Max retries exceeded"

    def _parse_scores(self, raw: str) -> Dict[str, float]:
        """Parse scored response from Gemini."""
        default = {
            "accuracy": 0, "completeness": 0, "helpfulness": 0,
            "avg_score": 0, "reasoning": "Failed to parse",
        }

        if "[Gemini Error]" in raw:
            default["reasoning"] = raw
            return default

        # Strip markdown code fences (Gemini often wraps in ```json ... ```)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            scores = json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                start = cleaned.find('{')
                end = cleaned.rfind('}')
                if start != -1 and end > start:
                    scores = json.loads(cleaned[start:end + 1])
                else:
                    default["reasoning"] = f"No JSON: {raw[:200]}"
                    return default
            except (json.JSONDecodeError, ValueError) as e:
                default["reasoning"] = f"Parse error: {e}. Raw: {raw[:200]}"
                return default

        try:
            result = {
                "accuracy": float(scores.get("accuracy", 0)),
                "completeness": float(scores.get("completeness", 0)),
                "helpfulness": float(scores.get("helpfulness", 0)),
                "reasoning": scores.get("reasoning", ""),
            }
            result["avg_score"] = round(
                (result["accuracy"] + result["completeness"] + result["helpfulness"]) / 3, 2
            )
            return result
        except (ValueError, KeyError) as e:
            default["reasoning"] = f"Score error: {e}"
            return default

    def _parse_pairwise(self, raw: str) -> Dict[str, str]:
        """Parse pairwise comparison response."""
        default = {"winner": "tie", "reasoning": "Failed to parse"}

        if "[Gemini Error]" in raw:
            default["reasoning"] = raw
            return default

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                start = cleaned.find('{')
                end = cleaned.rfind('}')
                if start != -1 and end > start:
                    data = json.loads(cleaned[start:end + 1])
                else:
                    return default
            except:
                return default

        winner = data.get("winner", "tie").upper()
        if winner not in ("A", "B", "TIE"):
            winner = "tie"

        return {
            "winner": winner,
            "reasoning": data.get("reasoning", ""),
        }


# ─────────────────────────────────────────────────────────
#  Legacy Qwen self-judge (kept for backward compatibility)
# ─────────────────────────────────────────────────────────

LEGACY_JUDGE_PROMPT = """You are evaluating the quality of a code assistant's answer.

## Question
{question}

## Code Context Summary
{context_summary}

## Answer Being Evaluated
{answer}

## Scoring Instructions

Rate the answer on these three dimensions using a 1-5 scale:

1. **Accuracy** (1-5): Is the answer factually correct based on the code context?
   - 1: Mostly incorrect or hallucinated
   - 3: Partially correct with some inaccuracies
   - 5: Fully accurate, all claims match the code

2. **Completeness** (1-5): Does the answer cover all important aspects?
   - 1: Misses most relevant information
   - 3: Covers the basics but misses important details
   - 5: Comprehensive coverage of the topic

3. **Helpfulness** (1-5): Would a developer find this answer useful?
   - 1: Not useful, too vague or confusing
   - 3: Somewhat useful, gives a general idea
   - 5: Very useful, actionable with specific references

Respond with ONLY a JSON object in this exact format:
{{"accuracy": <1-5>, "completeness": <1-5>, "helpfulness": <1-5>, "reasoning": "<brief explanation>"}}
"""


class LLMJudge:
    """Legacy Qwen-based judge (kept for backward compatibility)."""

    def __init__(self, generator=None):
        from graphcoderag.generation.generator import LLMGenerator
        self.generator = generator or LLMGenerator()

    def rate_answer(self, question, answer, context_summary="", reference_answer=""):
        ctx = context_summary or "(No context summary provided)"
        if reference_answer:
            ctx += f"\n\n## Reference Answer\n{reference_answer}"

        prompt = LEGACY_JUDGE_PROMPT.format(
            question=question,
            context_summary=ctx,
            answer=answer,
        )

        raw = self.generator.generate_raw(prompt=prompt, max_tokens=500, temperature=0.0)
        return self._parse_scores(raw)

    def _parse_scores(self, raw_response):
        default = {"accuracy": 0, "completeness": 0, "helpfulness": 0,
                    "avg_score": 0, "reasoning": "Failed to parse"}

        if "[LLM Error]" in raw_response:
            default["reasoning"] = raw_response
            return default

        try:
            scores = json.loads(raw_response.strip())
        except json.JSONDecodeError:
            try:
                start = raw_response.find('{')
                end = raw_response.rfind('}')
                if start != -1 and end > start:
                    scores = json.loads(raw_response[start:end + 1])
                else:
                    default["reasoning"] = f"No JSON found in: {raw_response[:200]}"
                    return default
            except (json.JSONDecodeError, ValueError) as e:
                default["reasoning"] = f"Parse error: {e}. Raw: {raw_response[:200]}"
                return default

        try:
            result = {
                "accuracy": float(scores.get("accuracy", 0)),
                "completeness": float(scores.get("completeness", 0)),
                "helpfulness": float(scores.get("helpfulness", 0)),
                "reasoning": scores.get("reasoning", ""),
            }
            result["avg_score"] = round(
                (result["accuracy"] + result["completeness"] + result["helpfulness"]) / 3, 2
            )
            return result
        except (ValueError, KeyError, AttributeError) as e:
            print(f"      [Judge Parse Error] {e} | Raw: {raw}", flush=True)
            default["reasoning"] = f"Score extraction error: {e}"
            return default

class OpenAIJudge(GeminiJudge):
    """Cross-model judge using OpenAI GPT for evaluation."""
    
    def __init__(self, api_key: str = None, model: str = None):
        import openai
        from graphcoderag.config import OPENAI_API_KEY
        
        self.api_key = api_key or OPENAI_API_KEY
        self.model_name = model or "gpt-4o-mini"
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
            
        self.client = openai.OpenAI(api_key=self.api_key)
        self._call_count = 0

    def _call_gemini(self, prompt: str, max_retries: int = 5) -> str:
        """Call OpenAI API (overrides _call_gemini to reuse parsing logic)."""
        import time
        for attempt in range(max_retries):
            try:
                self._call_count += 1
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    response_format={"type": "json_object"},
                    max_tokens=1024,
                    temperature=0.0,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                time.sleep(1)  # Pace calls
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e).lower()
                is_retryable = any(hint in error_str for hint in ["429", "rate", "overloaded", "529"])
                if is_retryable:
                    wait = 15 * (attempt + 1)
                    print(f"  [Judge] OpenAI rate limited, waiting {wait}s...", flush=True)
                    time.sleep(wait)
                elif attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    return f"[OpenAI Error] {e}"
        return "[OpenAI Error] Max retries exceeded"
