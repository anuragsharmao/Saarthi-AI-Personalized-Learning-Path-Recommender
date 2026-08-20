# [Saarthi AI - Your Guide to What's Next](https://saarthi-ai-personalized-learning-pa.vercel.app/)

**🔗 Live demo:** https://saarthi-ai-personalized-learning-pa.vercel.app/

A merged, bug-fixed, full-stack build combining three iterations into one:
a goal-taxonomy/skill-graph recommender with adaptive-assessment path
mutation, an LLM-first conversational layer with persistence-aware dashboard
insights, and a polished Tailwind frontend wired directly to the backend.
"Saarthi" (सारथी) means charioteer/guide — the AI acting as your guide
through a learning journey.

## Latest update: frontend swap + Groq instead of Anthropic

- Replaced the backend's LLM provider from Anthropic Claude to **Groq**
  (OpenAI-compatible endpoint, free tier). Default model is
  `openai/gpt-oss-20b` — Groq deprecated `llama-3.3-70b-versatile` and
  `llama-3.1-8b-instant` in June 2026, so those older model names are
  intentionally not used. Override via `GROQ_MODEL` in `.env`.
- Replaced the frontend entirely with the provided Tailwind/vanilla-JS
  design (landing → onboarding chat → dashboard → what-if / coach /
  assessment phases), with the "Hackathon Demo" badge removed.
- Fixed three real bugs found while wiring the new frontend to the backend:
  1. `document.getElementById('dashNextAction')` was referenced in JS but
     the element didn't exist in the HTML — `loadDashboard()` would throw
     and silently stop updating the page. Added the missing `<div
     id="dashNextAction">`.
  2. `/api/skill-gap/{id}` returned a `gaps` key; the frontend reads
     `data.skill_gaps`. Fixed the endpoint to return the key name the
     frontend actually expects (verified with a live request, not just
     read).
  3. `/api/job-analysis` returned `recommended_learning_order` /
     `custom_goal_label`; the frontend reads `data.gap_analysis
     .recommended_skills` and `data.custom_goal`. Fixed the endpoint to
     return both the old and new key names.
  4. The what-if weekly-hours simulator hardcoded a `10 hrs/week` baseline
     regardless of the learner's actual committed hours. Fixed to read
     `user.weekly_hours` — verified with two learners on different hour
     commitments to confirm it's reading the real value, not coincidentally
     matching the old constant.
- Added session persistence (`localStorage`) so refreshing the page doesn't
  lose the learner's session, and a small "Live AI (Groq) / offline mode"
  badge in the navbar so it's obvious which mode a demo is running in.
- `API_BASE` changed from a hardcoded `http://localhost:8000` to a relative
  path, since the frontend is served by the same FastAPI app.

All of the above was verified against a running server in this environment,
including a real (rejected) call to Groq's actual endpoint with an invalid
key to confirm the fallback path triggers on genuine failures, not just on
"no key present."


## Why this version, and what changed

You had two working prototypes. Here's what each contributed and what was
fixed when merging them into this single backend:

**From your FastAPI version (kept):**
- Multi-goal taxonomy (`GOAL_SKILL_MAPPING`) — 7 career goals, each with
  required vs. recommended skills, instead of one flat catalog.
- Market-demand scores per skill, factored into both ranking and explanations.
- Learning-style adaptation (visual / reading / hands-on / mixed) that
  re-weights resource recommendations.
- Accelerate / reinforce / relearn: assessment scores actually *mutate* the
  path in place (insert a practice milestone, insert prerequisite review
  milestones, or advance), not just a pass/fail gate.
- Job-description reverse engineering: paste a JD, get back the skills it
  implies and a prerequisite-ordered learning sequence.
- What-if simulation for goal switches and weekly-hours changes.

**Bugs fixed:**
- `analyze_job()` called `self._generate_job_path(...)` from a plain
  function (no `self` in scope) — this would 500 on every request. Fixed by
  calling the helper directly and moving it into `JobDescriptionService`.
- `.dict()` calls on Pydantic models were silently using the deprecated v1
  API under the v2 you had installed — switched to `.model_dump()`.
- The original goal-keyword matcher checked `"AI Engineer"` before
  `"Generative AI Engineer"`, so it always matched the shorter substring
  first and mis-classified generative-AI goals. Fixed by checking
  longer/more specific goal names first.

**From my earlier version, merged in:**
- Real Groq API calls (Llama/OSS models via Groq's free tier) for profile extraction,
  coaching, and job-description parsing — your version simulated these with
  keyword matching. Every one of these calls has a rule-based fallback, so
  the app still runs end-to-end with zero setup if no API key is present.
- A graph-based "what if I skip this skill?" simulator — walks the
  prerequisite graph to report exactly which downstream skills would become
  blocked, rather than a generic warning.
- Cohort percentile benchmarking against a simulated 150-learner demo cohort
  per goal (clearly labeled as simulated in the UI).
- Pacing-risk detection — compares committed weekly hours against actual
  completion rate and flags if you're falling behind your own plan.
- Spaced-repetition review nudges — flags completed milestones untouched for
  21+ days.
- A single `/api/chat` endpoint that transparently routes between onboarding
  (first message) and coaching (every message after), so the frontend only
  needs one call for the whole conversation — the granular endpoints
  (`/api/skill-gap`, `/api/recommendations`, etc.) are still there
  individually if you want to call them directly.

## File count (kept deliberately small)

```
saarthi-ai/
├── main.py              # entire backend: models, services, API routes
├── requirements.txt
├── .env.example
├── README.md
└── static/
    └── index.html       # entire frontend: HTML + CSS + JS, one file
```

Four files total. `main.py` is organized top-to-bottom as: Groq
integration → data models → in-memory "database" → skill graph → services
(profile extraction, skill-gap, recommendations, path generation,
adaptation, what-if, coaching, job-description, insights) → API routes.

## Running it

```bash
cd saarthi-ai
pip install -r requirements.txt
cp .env.example .env        # optional — see below
uvicorn main:app --reload
```

Open `http://localhost:8000`.

### With or without an API key

Copy `.env.example` to `.env` and set `GROQ_API_KEY` (free at console.groq.com) to enable live
Groq calls for profile extraction, coaching replies, and job-description
parsing. **Without a key, the app still runs completely** — every AI
touchpoint has a deterministic fallback (keyword/regex extraction, template
coaching replies), and the UI shows an "offline/heuristic mode" banner so
it's always clear which mode you're in.

## API surface

| Endpoint | Purpose |
|---|---|
| `POST /api/chat` | Conversational entry point — onboards on first message, coaches afterward |
| `POST /api/onboarding` | Extract a profile from free text and create a learner |
| `GET /api/learners/{id}` | Fetch a learner's profile + chat history |
| `POST /api/skill-gap/{id}` | Compute required-vs-current skill gaps |
| `POST /api/recommendations/{id}` | Ranked resource/project recommendations per gap |
| `POST /api/learning-path/{id}` | Generate/regenerate the full milestone path |
| `POST /api/assessment/{id}/{milestone_id}` | Submit a score → accelerate / reinforce / relearn |
| `POST /api/what-if/{id}` | Simulate a goal change, hours change, or skill skip |
| `POST /api/coach/{id}` | Ask the AI coach a direct question |
| `POST /api/job-analysis` | Reverse-engineer skills + order from a job description |
| `POST /api/learning-style/{id}` | Update visual/reading/hands-on/mixed preference |
| `GET /api/dashboard/{id}` | Progress, skill map, pacing risk, cohort percentile, reviews due |
| `POST /api/review/{id}/{milestone_id}` | Mark a completed milestone as reviewed |
| `POST /api/demo/create-user` | One-call demo learner for quick testing |
| `GET /api/health` | Reports whether live Groq calls are enabled |

## Data & persistence

In-memory (`Database` class in `main.py`), same as your original — resets on
restart. This was a deliberate choice to keep the file count down; every
service function takes/returns plain data, so swapping in Postgres/SQLite
only touches the `Database` class, nothing else.

## Known simplifications (be upfront about these if asked)

- Assessment questions are template-generated, not content-validated —
  fine for demonstrating the accelerate/reinforce/relearn mechanic, not a
  real question bank.
- The cohort used for percentile benchmarking is synthetic/simulated data
  generated at startup, clearly labeled as such in the UI — not real users.
- In-memory storage means all learners reset when the server restarts.