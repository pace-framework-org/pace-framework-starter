# PACE Framework

![PACE Framework](https://raw.githubusercontent.com/pace-framework-org/pace-docs/main/src/assets/pace-logo-square.svg)

**PACE** (Plan, Architect, Code, Evaluate) is an AI-native daily delivery framework that runs a structured pipeline of Claude-powered agents to implement, validate, and review software — one story per day, every day.

---

## What PACE Does

Each day, PACE runs five agents in sequence:

| Agent | Role | Output |
| --- | --- | --- |
| **PRIME** | Product — writes a focused Story Card from the sprint plan | `story.md` |
| **FORGE** | Engineering — implements the story using tool-use (read, write, run, commit) | `handoff.md` |
| **GATE** | Quality — validates implementation against acceptance criteria + CI | `gate.md` |
| **SENTINEL** | Security & SRE — reviews for vulnerabilities, reliability gaps, error paths | `sentinel.md` |
| **CONDUIT** | DevOps — reviews CI/CD pipelines, build scripts, infrastructure config | `conduit.md` |

Each agent can return **SHIP**, **HOLD**, or (for SENTINEL/CONDUIT) **ADVISORY**:

- **SHIP** — passes; next agent runs
- **HOLD** — blocks; FORGE gets up to 2 retries before escalation
- **ADVISORY** — non-blocking concern; FORGE gets one retry; if still advisory, backlocked

### Advisory Backlog

Non-critical findings are tracked in `.pace/advisory_backlog.yaml`. Every **7th day** is a **clearance day**: all open advisories become mandatory and FORGE must resolve them before SHIP.

### SCRIBE Prerequisite

Before Day 1, **SCRIBE** (a tool-use agent) reads your repository and optional documentation folder, then generates four context documents in `.pace/context/`:

| Document | Used by | Content |
| --- | --- | --- |
| `product.md` | PRIME | Vision, personas, MVP scope, success metrics |
| `engineering.md` | FORGE, GATE | Module map, tech stack, contracts, test patterns |
| `security.md` | SENTINEL | Threat model, trust boundaries, security requirements |
| `devops.md` | CONDUIT | CI/CD topology, env vars, runbook |

SCRIBE runs automatically if any document is missing (preflight check before each cycle).

---

## Setup

### 1. Configure your project

Edit `pace/pace.config.yaml`:

```yaml
product:
  name: "Your Product Name"
  description: >
    One-paragraph description of what the product does,
    who it's for, and what problem it solves.
  github_org: "your-org"

sprint:
  duration_days: 30

source:
  dirs:
    - name: "core"
      path: "src/"
      language: "Python"
      description: "Core application source"
  docs_dir: null   # Optional: path to external documentation folder

tech:
  primary_language: "Python 3.12"
  test_command: "pytest -v --tb=short"
  ci_system: "GitHub Actions"

platform:
  type: github   # github | gitlab | bitbucket | jenkins | local
```

### 2. Define your sprint plan

Edit `pace/plan.yaml` to define your 30-day sprint targets. Each day entry specifies:

```yaml
- day: 1
  week: 1
  week_label: "Foundation"
  target: "What FORGE must deliver today — specific and scope-limited"
  gate_criterion: "The binary test GATE uses to confirm delivery"
  human_gate: false
```

### 3. Configure your platform

Set credentials as environment variables (or CI/CD secrets) for your chosen platform:

**GitHub** (`platform.type: github`)

| Name | Type | Value |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Secret | Your Anthropic API key |
| `GITHUB_TOKEN` | Secret | Auto-provided by Actions (or a PAT with repo write) |
| `GITHUB_REPOSITORY` | Variable | `owner/repo` (auto-set in GitHub Actions) |
| `PACE_DAY` | Variable | Current day number (increment daily or automate) |
| `PACE_PAUSED` | Variable | `false` (set to `true` to pause the loop) |

**GitLab** (`platform.type: gitlab`)

| Name | Type | Value |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Secret | Your Anthropic API key |
| `GITLAB_TOKEN` | Secret | Personal access token or `CI_JOB_TOKEN` |
| `GITLAB_PROJECT` | Variable | `group/project` slug |
| `GITLAB_URL` | Variable | GitLab instance URL (default: `https://gitlab.com`) |
| `PACE_DAY` | Variable | Current day number |
| `PACE_PAUSED` | Variable | `false` |

**Bitbucket** (`platform.type: bitbucket`)

| Name | Type | Value |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Secret | Your Anthropic API key |
| `BITBUCKET_USER` | Secret | Bitbucket username |
| `BITBUCKET_APP_PASSWORD` | Secret | App password (Repositories:Write, Pull requests:Write, Issues:Write, Pipelines:Read) |
| `BITBUCKET_WORKSPACE` | Variable | Workspace slug |
| `BITBUCKET_REPO_SLUG` | Variable | Repository slug |
| `PACE_DAY` | Variable | Current day number |
| `PACE_PAUSED` | Variable | `false` |

> Bitbucket Cloud only. Issues must be enabled on the repo (Settings → Issue tracker). Pipelines must be enabled for CI polling.

**Jenkins** (`platform.type: jenkins`)

| Name | Type | Value |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Secret | Your Anthropic API key |
| `JENKINS_URL` | Variable | Base URL of the Jenkins instance |
| `JENKINS_USER` | Secret | Username for HTTP Basic auth |
| `JENKINS_TOKEN` | Secret | API token (User → Configure → API Token) |
| `JENKINS_JOB_NAME` | Variable | Full job path (e.g. `my-folder/my-pipeline`) |
| `PACE_DAY` | Variable | Current day number |
| `PACE_PAUSED` | Variable | `false` |

> Jenkins has no native PR/issue concept. Review gates and escalations are written to local `.pace/` files. Consider pairing with GitHub or GitLab for those operations.

**Local** (`platform.type: local`)

No credentials required. CI polling is skipped; review gates and escalations are written to `.pace/day-N/review-pr.md` and `.pace/day-N/escalation-issue.md`.

### 4. Set up your build environment

**GitHub Actions:** open `.github/workflows/pace.yml` and uncomment/add setup steps for your tech stack (Go, Node, Python, Rust, etc.).

**GitLab CI:** create `.gitlab-ci.yml` that runs `python pace/orchestrator.py` on a schedule.

**Bitbucket Pipelines:** create `bitbucket-pipelines.yml` that runs `python pace/orchestrator.py` on a schedule.

**Jenkins:** create a pipeline job or `Jenkinsfile` that runs `python pace/orchestrator.py`.

### 5. Run PACE

Trigger the pipeline on your platform (push to `main`, scheduled cron, or manual dispatch). PACE will run the full daily cycle automatically.

---

## Platform Adapters

PACE decouples its agent pipeline from the underlying CI/CD and Git hosting platform through a **platform adapter interface**. Each adapter implements five operations:

| Operation | What it does |
| --- | --- |
| `open_review_pr` | Opens a PR / MR for human gate days |
| `open_escalation_issue` | Opens an issue / ticket when retries are exhausted |
| `wait_for_commit_ci` | Polls CI until the commit reaches a terminal state |
| `post_daily_summary` | Posts a one-line status notification |
| `write_job_summary` | Writes the full markdown report to the platform's summary UI |

### Platform support matrix

| Platform | PR / MR | Issue | CI polling | Job summary |
| --- | --- | --- | --- | --- |
| **GitHub** | GitHub Pull Request | GitHub Issue | GitHub Actions (by SHA) | `$GITHUB_STEP_SUMMARY` |
| **GitLab** | GitLab Merge Request | GitLab Issue | GitLab Pipelines (by SHA) | `$CI_JOB_SUMMARY` / file |
| **Bitbucket** | Bitbucket Pull Request | Bitbucket Issue | Bitbucket Pipelines (by SHA) | `pace-summary.md` |
| **Jenkins** | Local file (`.pace/`) | Local file (`.pace/`) | Jenkins REST API (by SHA) | `jenkins-summary.md` |
| **Local** | Local file (`.pace/`) | Local file (`.pace/`) | Skipped (`no_runs`) | `pace-summary.md` |

The active adapter is selected from `platform.type` in `pace.config.yaml`. To add a new platform, create a class that extends `PlatformAdapter` in `pace/platforms/` and register it in `pace/platforms/__init__.py`.

---

## LLM Providers

PACE decouples its agents from any specific AI provider through an **LLM adapter interface**. All six agents (PRIME, FORGE, GATE, SENTINEL, CONDUIT, SCRIBE) call the adapter — never an SDK directly.

### The two-method contract

| Method | Used by | What it does |
| --- | --- | --- |
| `complete(system, user)` | PRIME, GATE, SENTINEL, CONDUIT | Single-turn completion — returns a text string |
| `chat(system, messages, tools)` | FORGE, SCRIBE | One step in an agentic tool loop — returns a `ChatResponse` |

### Supported providers

| Provider | `llm.provider` | `llm.model` example | Key env var |
| --- | --- | --- | --- |
| **Anthropic** *(default)* | `anthropic` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| **OpenAI** | `litellm` | `openai/gpt-4o` | `OPENAI_API_KEY` |
| **Google Gemini** | `litellm` | `gemini/gemini-2.0-flash` | `GEMINI_API_KEY` |
| **AWS Bedrock** | `litellm` | `bedrock/anthropic.claude-sonnet-4-6` | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` |
| **Azure OpenAI** | `litellm` | `azure/gpt-4o` | `AZURE_API_KEY` + `AZURE_API_BASE` |
| **Groq** | `litellm` | `groq/llama-3.1-70b-versatile` | `GROQ_API_KEY` |
| **Mistral** | `litellm` | `mistral/mistral-large-latest` | `MISTRAL_API_KEY` |
| **Ollama** (local) | `litellm` | `ollama/llama3.1` | none (set `llm.base_url`) |

The `litellm` provider routes to any of the above (and [100+ more](https://docs.litellm.ai/docs/providers)) through a unified interface, handling tool-calling format differences automatically.

### Switching providers

Edit two lines in `pace/pace.config.yaml`:

```yaml
llm:
  provider: litellm
  model: openai/gpt-4o
```

Set the provider's API key in your environment. No agent code changes required.

### Adding a new provider

Extend `LLMAdapter` in `pace/llm/` and register it in `pace/llm/__init__.py`:

```python
class MyProviderAdapter(LLMAdapter):
    def complete(self, system, user, max_tokens=4096) -> str: ...
    def chat(self, system, messages, tools=None, max_tokens=8192) -> ChatResponse: ...
```

---

## Local Development

```bash
# Install core + default provider (Anthropic)
cd pace
pip install anthropic PyYAML jsonschema PyGithub

# Or install everything
pip install -r requirements.txt

# Run a cycle locally — platform: local, llm: anthropic
ANTHROPIC_API_KEY=sk-... PACE_DAY=1 python orchestrator.py

# Run with OpenAI via LiteLLM
# (set llm.provider: litellm, llm.model: openai/gpt-4o in pace.config.yaml)
OPENAI_API_KEY=sk-... PACE_DAY=1 python orchestrator.py

# Run with Ollama (no API key; set llm.model: ollama/llama3.1, llm.base_url: http://localhost:11434)
PACE_DAY=1 python orchestrator.py

# Run SCRIBE manually to generate context documents
python -c "from agents.scribe import run_scribe; run_scribe()"
```

---

## Repository Structure

```text
pace-framework-starter/
├── pace/
│   ├── pace.config.yaml        # Project identity, tech stack, and platform config
│   ├── plan.yaml               # 30-day sprint plan (day targets and gate criteria)
│   ├── orchestrator.py         # Main entry point — drives the daily cycle
│   ├── config.py               # Loads pace.config.yaml into PaceConfig dataclass
│   ├── schemas.py              # JSON schemas for all agent outputs
│   ├── advisory.py             # Advisory backlog management
│   ├── preflight.py            # SCRIBE prerequisite check
│   ├── reporter.py             # Job summary builder and PROGRESS.md writer
│   ├── requirements.txt        # Python dependencies
│   ├── llm/
│   │   ├── base.py             # LLMAdapter ABC + ToolCall + ChatResponse
│   │   ├── anthropic_adapter.py# AnthropicAdapter (default)
│   │   ├── litellm_adapter.py  # LiteLLMAdapter (OpenAI, Gemini, Bedrock, Ollama, ...)
│   │   └── __init__.py         # Factory: get_llm_adapter()
│   ├── platforms/
│   │   ├── base.py             # PlatformAdapter abstract base class
│   │   ├── github.py           # GitHubAdapter — Actions CI + GitHub API
│   │   ├── gitlab.py           # GitLabAdapter — GitLab CI + GitLab API
│   │   ├── bitbucket.py        # BitbucketAdapter — Pipelines + Bitbucket API
│   │   ├── jenkins.py          # JenkinsAdapter — Jenkins REST API
│   │   ├── local.py            # LocalAdapter — no-op / file-based
│   │   └── __init__.py         # Factory: get_platform_adapter()
│   └── agents/
│       ├── prime.py            # PRIME — Story Card generation
│       ├── forge.py            # FORGE — agentic implementation loop
│       ├── gate.py             # GATE — acceptance criteria validation
│       ├── sentinel.py         # SENTINEL — security and SRE review
│       ├── conduit.py          # CONDUIT — DevOps and CI/CD review
│       └── scribe.py           # SCRIBE — context document generation
├── .pace/
│   ├── context/                # Generated by SCRIBE (product/engineering/security/devops.md)
│   └── day-N/                  # Per-day artifacts (story.md, handoff.md, gate.md, ...)
├── .github/
│   └── workflows/
│       └── pace.yml            # GitHub Actions workflow (language-agnostic template)
├── PROGRESS.md                 # Auto-updated sprint progress tracker
└── README.md
```

---

## Pipeline Decision Logic

```text
PRIME → FORGE → GATE → SENTINEL → CONDUIT
                  |         |           |
                HOLD      HOLD        HOLD    → retry FORGE (up to 2 retries)
                        ADVISORY    ADVISORY  → retry FORGE once; then backlock
                 SHIP      SHIP        SHIP   → commit artifacts, update PROGRESS.md
```

After `MAX_RETRIES` (2) failed cycles, the orchestrator:

1. Writes an `escalated` marker in the day directory
2. Opens a platform issue (GitHub Issue, GitLab Issue, Bitbucket Issue, or local file)
3. Sets `PACE_PAUSED=true` (or instructs the operator to do so)

The loop resumes once the issue is resolved and `PACE_PAUSED` is unset.

---

## Human Gate Days

Set `human_gate: true` on any day in `plan.yaml` to pause the loop and open a review PR/MR. The orchestrator stops after opening the PR/MR. Merge it to resume.

Recommended gates: Day 14 (end of Week 2) and Day 28 (end of Week 4).

---

## Customizing Agents

Each agent's system prompt is built dynamically from `pace.config.yaml`. To change agent behavior:

- **PRIME**: Edit the story format instructions in `agents/prime.py`
- **FORGE**: Modify `ALLOWED_PREFIXES` / `BLOCKED_PATTERNS` in `agents/forge.py` for your build toolchain
- **GATE**: The test command comes from `pace.config.yaml → tech.test_command`
- **SENTINEL**: Add project-specific security requirements to the system prompt
- **CONDUIT**: Extend the DevOps checklist for your deployment targets
- **SCRIBE**: The `DOC_MAPPING` in `agents/scribe.py` guides what to look for in each doc segment

---

## Acknowledgements

PACE Framework is an independent, generalized AI delivery framework.
Built with [Anthropic Claude](https://anthropic.com) and the [Claude API](https://docs.anthropic.com).
