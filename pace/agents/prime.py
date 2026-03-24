"""PRIME agent — generates Story Cards from the sprint plan target."""

import re
import yaml
import jsonschema
from pathlib import Path
from schemas import STORY_CARD_SCHEMA
from config import load_config
from llm import get_analysis_adapter

REPO_ROOT = Path(__file__).parent.parent.parent
PACE_DIR = REPO_ROOT / ".pace"

_VALID_YAML_ESCAPES = set('0abttnvfeN_LP "\\/')


def _load_context(doc: str) -> str:
    path = PACE_DIR / "context" / doc
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _load_deferred_scope(day: int) -> str:
    """Return deferred_scope.yaml content from the previous day, if it exists."""
    path = PACE_DIR / f"day-{day - 1}" / "deferred_scope.yaml"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _clean_yaml(text: str) -> str:
    match = re.search(r"```(?:yaml)?\s*(.*?)```", text, re.DOTALL)
    yaml_text = match.group(1).strip() if match else text.strip()
    return re.sub(
        r'\\(.)',
        lambda m: m.group(0) if m.group(1) in _VALID_YAML_ESCAPES else m.group(1),
        yaml_text,
    )


def run_prime_refine(day: int, story_card: dict, reason: str, max_ac: int) -> tuple[dict, list[str]]:
    """Re-invoke PRIME to split an oversized story into today + deferred.

    Returns:
        (refined_story_card, deferred_acceptance_criteria)
    """
    cfg = load_config()
    adapter = get_analysis_adapter()
    story_yaml = yaml.dump(story_card, default_flow_style=False, allow_unicode=True)

    system_prompt = f"""You are the Product Agent (PRIME) for {cfg.product_name}.

A story card has been flagged for refinement before coding begins:
{reason}

Split this story into two parts:
1. TODAY: keep the highest-value acceptance criteria, at most {max_ac}.
2. DEFERRED: all remaining acceptance criteria, verbatim.

Rules:
- TODAY must be a complete, shippable slice with {max_ac} or fewer acceptance criteria.
- Prefer foundational criteria today; defer additive/optional ones.
- Rewrite the story/given/when/then to match today's reduced scope.
- out_of_scope must include "Remaining criteria deferred to next day."
- DEFERRED lists every criterion that did not fit, copied verbatim.
- Respond ONLY with this YAML structure — no other text:

```yaml
today:
  day: <integer>
  agent: PRIME
  story: "..."
  given: "..."
  when: "..."
  then: "..."
  acceptance:
    - "..."
  out_of_scope:
    - "Remaining criteria deferred to next day"
deferred:
  - "Deferred criterion 1"
```"""

    user_message = f"""Day: {day}
Original story card to split:
{story_yaml}
Split into today's story (≤{max_ac} AC) and deferred criteria for next day."""

    raw = adapter.complete(system_prompt, user_message, max_tokens=2048).strip()
    result = yaml.safe_load(_clean_yaml(raw))
    today_card = result.get("today", {})
    today_card["day"] = day
    today_card["agent"] = "PRIME"
    deferred = result.get("deferred", [])
    jsonschema.validate(today_card, STORY_CARD_SCHEMA)
    return today_card, deferred


def run_prime(day: int, target: str, recent_gates: list[str]) -> dict:
    cfg = load_config()
    adapter = get_analysis_adapter()

    system_prompt = f"""You are the Product Agent (PRIME) for {cfg.product_name}.

{cfg.product_description}

Your only job is to produce a Story Card for today's delivery cycle.
Read the story target from the plan and the last 3 gate reports.
Write a Story Card that is specific, testable, and completable in one day.

You MUST respond with ONLY a valid YAML block — no prose before or after. Format:

```yaml
day: <integer>
agent: PRIME
story: "As a [persona], when I [action], [outcome]."
given: "Starting state description"
when: "The action taken"
then: "Observable, verifiable outcome"
acceptance:
  - "Criterion 1 — specific and binary"
  - "Criterion 2 — specific and binary"
out_of_scope:
  - "What is explicitly deferred"
```

Rules:
- Every acceptance criterion must be verifiable by an automated test or CLI command.
- If the plan target is larger than one day, scope it down. Record the reduction in out_of_scope.
- Do not invent requirements not in the plan. Do not defer items already in the plan.
- Respond with ONLY the yaml block. No other text."""

    if recent_gates:
        gates_context = "\n\n".join(
            f"--- Gate Report Day {day - len(recent_gates) + i} ---\n{g}"
            for i, g in enumerate(recent_gates)
        )
    else:
        gates_context = "No previous gate reports — this is Day 1."

    product_ctx = _load_context("product.md")
    product_section = f"\nProduct Context:\n{product_ctx}\n" if product_ctx else ""

    deferred_ctx = _load_deferred_scope(day)
    deferred_section = (
        f"\nDeferred scope from Day {day - 1} (incorporate these into today's story):\n{deferred_ctx}\n"
        if deferred_ctx else ""
    )

    user_message = f"""Day: {day}
Today's story target from the plan: {target}
{deferred_section}{product_section}
Recent gate reports for context:
{gates_context}

Produce the Story Card YAML for Day {day}."""

    last_error: Exception | None = None
    for attempt in range(3):
        retry_note = (
            f"\n\nPrevious attempt failed validation: {last_error}. "
            "Ensure 'acceptance' is a non-empty YAML list with at least one item."
            if last_error else ""
        )
        raw = adapter.complete(system_prompt, user_message + retry_note, max_tokens=2048).strip()
        story_card = yaml.safe_load(_clean_yaml(raw))
        if not isinstance(story_card, dict):
            last_error = ValueError(f"Expected dict, got {type(story_card).__name__}")
            continue
        story_card["day"] = day
        story_card["agent"] = "PRIME"
        # Coerce None acceptance to empty list so schema gives a clear minItems error
        if story_card.get("acceptance") is None:
            story_card["acceptance"] = []
        try:
            jsonschema.validate(story_card, STORY_CARD_SCHEMA)
            return story_card
        except jsonschema.ValidationError as exc:
            last_error = exc

    raise last_error
