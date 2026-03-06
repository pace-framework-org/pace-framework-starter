"""PRIME agent — generates Story Cards from the sprint plan target."""

import re
import yaml
import jsonschema
from pathlib import Path
from schemas import STORY_CARD_SCHEMA
from config import load_config
from llm import get_llm_adapter

REPO_ROOT = Path(__file__).parent.parent.parent


def _load_context(doc: str) -> str:
    path = REPO_ROOT / ".pace" / "context" / doc
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_prime(day: int, target: str, recent_gates: list[str]) -> dict:
    cfg = load_config()
    adapter = get_llm_adapter()

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

    user_message = f"""Day: {day}
Today's story target from the plan: {target}
{product_section}
Recent gate reports for context:
{gates_context}

Produce the Story Card YAML for Day {day}."""

    raw = adapter.complete(system_prompt, user_message, max_tokens=2048).strip()
    match = re.search(r"```(?:yaml)?\s*(.*?)```", raw, re.DOTALL)
    yaml_text = match.group(1).strip() if match else raw

    story_card = yaml.safe_load(yaml_text)
    story_card["day"] = day
    story_card["agent"] = "PRIME"

    jsonschema.validate(story_card, STORY_CARD_SCHEMA)
    return story_card
