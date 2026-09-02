# Saarthi AI — Your Guide to What's Next

**Saarthi (सारथी)** means *guide* or *charioteer*. The idea behind Saarthi AI is simple: instead of giving learners a fixed list of courses, it builds a learning path based on their **career goal, existing skills, learning style, available time, and progress**.

🔗 **Live Demo:** https://saarthi-ai-personalized-learning-pa.vercel.app/

---

## What is Saarthi AI?

Saarthi AI is a full-stack personalized learning-path platform.

A learner can describe their goal in normal language, for example:

> "I want to become a Generative AI Engineer. I know Python and basic machine learning, but I haven't worked with LLMs yet."

Saarthi extracts the learner's profile, identifies the missing skills, and creates a learning path around those gaps.

The path isn't completely static either. As the learner completes assessments, the system can **accelerate, reinforce, or relearn** parts of the path depending on their performance.

It also supports job-description analysis, so a learner can paste a real JD and see what skills it requires and what order they should learn them in.

---

## Main Features

### 🎯 Personalized Skill Gap Analysis

Saarthi maps different career goals to their required and recommended skills.

It compares those skills with the learner's existing knowledge and identifies what they need to learn next.

The system also considers **market-demand scores** when ranking skills, so the path isn't based only on a fixed skill list.

---

### 🧠 Adaptive Learning Paths

The learning path changes based on assessment performance.

There are three possible outcomes:

* **Accelerate** — the learner already understands the topic, so the path moves forward.
* **Reinforce** — the learner needs additional practice before moving ahead.
* **Relearn** — prerequisite concepts are added back into the path.

This makes the learning path adaptive instead of just being a predefined course sequence.

---

### 📚 Learning-Style Based Recommendations

Learners can select how they prefer to learn:

* Visual
* Reading
* Hands-on
* Mixed

The recommendation system uses this preference when ranking learning resources and projects.

---

### 💬 AI Learning Coach

Saarthi includes a conversational AI layer powered by **Groq**.

The coach can answer questions about the learner's current path, suggest what to focus on next, and provide guidance based on their progress.

The same `/api/chat` endpoint handles both onboarding and subsequent coaching conversations.

If the Groq API isn't configured or a request fails, Saarthi falls back to a rule-based response so the application can still be used.

---

### 💼 Job Description Analysis

A learner can paste a job description and Saarthi will try to identify:

1. Skills mentioned or implied by the JD
2. Skills the learner needs
3. A prerequisite-aware learning order

This turns a job description into a practical learning roadmap.

---

### 🔄 What-If Simulator

The learner can experiment with different scenarios without changing their actual learning plan.

For example:

* What if I switch my career goal?
* What if I can study 15 hours instead of 10 hours per week?
* What happens if I skip a particular skill?

For skipped skills, Saarthi follows the prerequisite graph and shows which later skills could become blocked.

---

### 📊 Learning Dashboard

The dashboard provides a quick overview of:

* Overall learning progress
* Current skill gaps
* Skill map
* Next recommended action
* Pacing risk
* Cohort percentile
* Reviews that are due

The cohort percentile is based on a **simulated demo cohort**, not real user data.

---

### 🔁 Spaced Review

Completed milestones can be marked as reviewed.

If a completed milestone hasn't been reviewed for 21+ days, Saarthi can surface it as a review reminder.

---

## Tech Stack

### Backend

* Python
* FastAPI
* Pydantic
* Groq API

### Frontend

* HTML
* Tailwind CSS
* Vanilla JavaScript

### AI / Recommendation

* Groq LLM
* Goal → skill taxonomy
* Skill prerequisite graph
* TF-IDF / ranking-based recommendations
* Rule-based fallbacks

### Deployment

* Frontend/backend served through the FastAPI application
* Live demo deployed on Vercel

---

## How the System Works

The basic flow looks like this:

```text
Learner
   │
   ▼
Natural Language Goal
   │
   ▼
Profile Extraction
   │
   ├── Career Goal
   ├── Existing Skills
   ├── Learning Style
   └── Weekly Study Hours
   │
   ▼
Skill Gap Analysis
   │
   ▼
Prerequisite Skill Graph
   │
   ▼
Personalized Learning Path
   │
   ├── Resources
   ├── Projects
   └── Assessments
   │
   ▼
Assessment Result
   │
   ├── Accelerate
   ├── Reinforce
   └── Relearn
   │
   ▼
Updated Learning Path
```

---

## Groq Integration

The current version uses **Groq** instead of Anthropic.

The default model is:

```text
openai/gpt-oss-20b
```

The model can be changed through:

```env
GROQ_MODEL=your-model-name
```

The application does not completely depend on the LLM.

If `GROQ_API_KEY` isn't available, Saarthi switches to deterministic fallbacks for things such as profile extraction and coaching responses.

This also makes it easier to run the project locally without setting up an API key first.

---

## Project Structure

I intentionally kept the project small so that the core logic is easy to understand.

```text
saarthi-ai/
│
├── main.py
├── requirements.txt
├── .env.example
├── README.md
│
└── static/
    └── index.html
```

### `main.py`

Contains the backend, including:

* Data models
* In-memory database
* Goal and skill taxonomy
* Skill graph
* Profile extraction
* Skill-gap analysis
* Recommendations
* Learning-path generation
* Assessment adaptation
* What-if simulation
* AI coaching
* Job-description analysis
* Dashboard insights
* API routes

### `static/index.html`

Contains the complete frontend:

* Landing page
* Onboarding chat
* Dashboard
* Learning path
* Coach
* Assessment
* What-if simulator

---

## Running Locally

Clone the repository and install the dependencies:

```bash
cd saarthi-ai
pip install -r requirements.txt
```

Create the environment file:

```bash
cp .env.example .env
```

Add your Groq API key if you want to use live AI responses:

```env
GROQ_API_KEY=your_api_key
```

Then start the server:

```bash
uvicorn main:app --reload
```

Open:

```text
http://localhost:8000
```

### Running without a Groq API key

You can also run Saarthi without an API key.

The application uses rule-based fallbacks for the AI-dependent parts, so the main learning-path workflow still works.

The UI indicates whether the application is currently running in **Live AI** or **offline/heuristic** mode.

---

## API Endpoints

| Endpoint                                   | Purpose                                |
| ------------------------------------------ | -------------------------------------- |
| `POST /api/chat`                           | Onboarding and AI coaching             |
| `POST /api/onboarding`                     | Create a learner from free-form input  |
| `GET /api/learners/{id}`                   | Get learner profile and chat history   |
| `POST /api/skill-gap/{id}`                 | Calculate skill gaps                   |
| `POST /api/recommendations/{id}`           | Get recommendations for missing skills |
| `POST /api/learning-path/{id}`             | Generate/regenerate learning path      |
| `POST /api/assessment/{id}/{milestone_id}` | Submit an assessment                   |
| `POST /api/what-if/{id}`                   | Run what-if simulations                |
| `POST /api/coach/{id}`                     | Ask the AI coach                       |
| `POST /api/job-analysis`                   | Analyze a job description              |
| `POST /api/learning-style/{id}`            | Update learning preference             |
| `GET /api/dashboard/{id}`                  | Get dashboard insights                 |
| `POST /api/review/{id}/{milestone_id}`     | Mark a milestone as reviewed           |
| `POST /api/demo/create-user`               | Create a demo learner                  |
| `GET /api/health`                          | Check AI/backend status                |

---

## Important Implementation Details

During the merge of the different versions of Saarthi, a few issues had to be fixed.

### Frontend/backend response mismatch

The frontend expected:

```text
skill_gaps
```

while the backend was returning:

```text
gaps
```

The API response was updated so both sides use the same structure.

### Job analysis response mismatch

The frontend expected:

```text
gap_analysis.recommended_skills
gap_analysis.custom_goal
```

while the backend was returning different field names.

The response was updated to support the frontend while keeping the existing fields for compatibility.

### Missing dashboard element

The JavaScript referenced:

```text
dashNextAction
```

but the element wasn't present in the HTML.

Adding the missing element fixed the dashboard update issue.

### Pydantic v2

The older `.dict()` calls were replaced with `.model_dump()` to match Pydantic v2.

### Goal matching

The goal matcher originally checked broader goals before more specific ones.

For example, `"AI Engineer"` could match before `"Generative AI Engineer"`.

The matching order was changed to check more specific goal names first.

### What-if weekly hours

The simulator originally used a fixed 10 hours/week value.

It now uses the learner's actual weekly commitment instead.

---

## Data & Persistence

At the moment, Saarthi uses an **in-memory database**.

This was intentional for keeping the prototype simple.

The advantage is that the project can run with almost no database setup.

The downside is that learner data is lost when the backend restarts.

The database layer is kept separate from the services, so replacing it with **SQLite, PostgreSQL, or another database** later shouldn't require rewriting the recommendation and learning-path logic.

---

## Current Limitations

Saarthi is still a prototype, so there are a few things I would improve before using it as a production learning platform.

### Assessment Question Quality

Assessment questions are currently generated from templates.

They demonstrate the adaptive learning mechanism, but they aren't a professionally validated question bank.

### Synthetic Cohort

The cohort percentile feature uses simulated learner data generated for the demo.

It should not be interpreted as a comparison against real Saarthi users.

### In-Memory Storage

Learner information is currently stored in memory and is lost when the server restarts.

A persistent database would be the next obvious improvement.

### Learning Resources

The recommendation system currently focuses on matching skills and learner preferences. A future version could integrate live course/resource data and continuously update recommendations based on market demand.

---

## What's Next?

Some improvements I'd like to work on:

* PostgreSQL-based persistence
* Real learner analytics
* Better assessment/question generation
* More detailed skill graphs
* Real-time market-demand data
* More learning resources and project recommendations
* Authentication and user accounts
* Better progress analytics
* More robust LLM evaluation
* Resource completion tracking

---

## Why I Built Saarthi

Most learning platforms give you a collection of courses and leave you to figure out **what to learn next**.

Saarthi is built around the opposite idea:

> **Start with where you want to go, understand where you are now, and figure out the path between the two.**

The goal is not to replace existing learning platforms. It's to make the journey between **career goal → skill gaps → learning path → progress → next step** more personalized.

---

## License

This project is for learning, experimentation, and demonstration purposes.
