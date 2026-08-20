# main.py — Saarthi AI: AI-Powered Personalized Learning Path Recommender
# Run with: uvicorn main:app --reload
#
# This is a merged, bug-fixed, single-file backend combining:
#   - the original goal-taxonomy / skill-graph / adaptive-assessment design
#     (multi-goal mapping, learning-style adaptation, market demand scores,
#      accelerate/reinforce/relearn path mutation, job-description reverse
#      engineering, what-if simulation)
#   - real Groq (Llama/OSS) API integration for every "AI" touchpoint (profile
#     extraction, coaching, job-description parsing), each with a
#     deterministic rule-based fallback so the app runs with or without a key
#   - persistence-free but session-durable cohort benchmarking, spaced-
#     repetition review nudges, and pacing-risk detection
#
# Data is in-memory (a dict-backed "database") for demo purposes — swap
# `DB` for a real datastore in production; every service function takes
# plain data in and returns plain data out, so that swap is contained to
# the `DB` class only.

import os
import re
import json
import uuid
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# ============================================================
# APP SETUP
# ============================================================

app = FastAPI(title="Saarthi AI", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ============================================================
# GROQ INTEGRATION — every AI touchpoint has a rule-based
# fallback, so the whole app still runs end to end with no key.
# Groq's chat completions API is OpenAI-compatible. Default model
# is openai/gpt-oss-20b — Groq deprecated llama-3.3-70b-versatile
# and llama-3.1-8b-instant in June 2026; gpt-oss-20b/120b are the
# current recommended free-tier models. Override with GROQ_MODEL.
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
HAS_KEY = bool(GROQ_API_KEY)


async def call_llm(system: str, user_text: str, max_tokens: int = 800) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()


def strip_fences(raw: str) -> str:
    return raw.replace("```json", "").replace("```", "").strip()


# ============================================================
# DATA MODELS
# ============================================================

class UserProfile(BaseModel):
    id: str
    name: str
    goal: str
    experience_level: str
    weekly_hours: int
    deadline_months: int
    learning_style: str = "mixed"
    skills: Dict[str, float] = Field(default_factory=dict)
    interests: List[str] = Field(default_factory=list)
    completed_milestones: List[str] = Field(default_factory=list)
    current_phase: int = 0
    is_synthetic: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Resource(BaseModel):
    id: str
    title: str
    type: str
    skills: List[str]
    difficulty: str
    duration_hours: int
    prerequisites: List[str]
    description: str


class Milestone(BaseModel):
    id: str
    title: str
    phase: int
    skills: List[str]
    resources: List[Resource]
    project: Dict
    assessment: Dict
    estimated_hours: int
    completed: bool = False
    score: Optional[float] = None
    completed_at: Optional[datetime] = None
    last_reviewed_at: Optional[datetime] = None


class LearningPath(BaseModel):
    user_id: str
    goal: str
    milestones: List[Milestone]
    total_hours: int
    estimated_completion: datetime
    current_phase: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# IN-MEMORY "DATABASE"
# ============================================================

class Database:
    def __init__(self):
        self.users: Dict[str, UserProfile] = {}
        self.paths: Dict[str, LearningPath] = {}
        self.chat_history: Dict[str, List[Dict]] = {}
        self.quiz_cache: Dict[str, List[Dict]] = {}  # "user_id:milestone_id" -> answer key

    def get_user(self, user_id):
        return self.users.get(user_id)

    def save_user(self, user: UserProfile):
        self.users[user.id] = user
        return user

    def get_path(self, user_id):
        return self.paths.get(user_id)

    def save_path(self, path: LearningPath):
        self.paths[path.user_id] = path
        return path


DB = Database()

# ============================================================
# SKILL GRAPH  (kept from the original design; demand_score
# drives both recommendation ranking and explanation copy)
# ============================================================

class SkillNode(BaseModel):
    name: str
    category: str
    prerequisites: List[str]
    difficulty: str
    demand_score: float = 0.5
    resources: List[Dict] = Field(default_factory=list)
    projects: List[Dict] = Field(default_factory=list)


def build_skill_graph() -> Dict[str, SkillNode]:
    raw = {
        "Python": dict(category="Programming", prerequisites=[], difficulty="beginner", demand_score=0.95,
                       resources=[{"title": "Python for Everybody", "type": "course", "hours": 20},
                                  {"title": "Python Crash Course", "type": "book", "hours": 15}],
                       projects=[{"title": "Calculator App", "difficulty": "beginner"}]),
        "SQL": dict(category="Data", prerequisites=[], difficulty="beginner", demand_score=0.85,
                    resources=[{"title": "SQL for Data Science", "type": "course", "hours": 12}],
                    projects=[{"title": "Database Design Project", "difficulty": "beginner"}]),
        "Statistics": dict(category="Data", prerequisites=["Python"], difficulty="intermediate", demand_score=0.7,
                            resources=[{"title": "Statistics for ML", "type": "course", "hours": 15}],
                            projects=[{"title": "Statistical Analysis Project", "difficulty": "intermediate"}]),
        "Machine Learning": dict(category="AI/ML", prerequisites=["Python", "Statistics"], difficulty="intermediate", demand_score=0.9,
                                  resources=[{"title": "ML Specialization", "type": "course", "hours": 40}],
                                  projects=[{"title": "Housing Price Predictor", "difficulty": "intermediate"}]),
        "Neural Networks": dict(category="AI/ML", prerequisites=["Python", "Machine Learning"], difficulty="intermediate", demand_score=0.8,
                                 resources=[{"title": "Neural Networks Zero to Hero", "type": "course", "hours": 30}],
                                 projects=[{"title": "Neural Net from Scratch", "difficulty": "intermediate"}]),
        "Deep Learning": dict(category="AI/ML", prerequisites=["Python", "Machine Learning", "Neural Networks"], difficulty="intermediate", demand_score=0.85,
                               resources=[{"title": "Deep Learning Specialization", "type": "course", "hours": 45}],
                               projects=[{"title": "Image Classifier", "difficulty": "intermediate"}]),
        "Computer Vision": dict(category="AI/ML", prerequisites=["Deep Learning", "Python"], difficulty="advanced", demand_score=0.8,
                                 resources=[{"title": "Computer Vision with PyTorch", "type": "course", "hours": 30}],
                                 projects=[{"title": "Object Detection System", "difficulty": "advanced"}]),
        "Transformers": dict(category="AI/ML", prerequisites=["Deep Learning"], difficulty="advanced", demand_score=0.9,
                              resources=[{"title": "Hugging Face Transformers", "type": "course", "hours": 25}],
                              projects=[{"title": "Sentiment Analysis with BERT", "difficulty": "advanced"}]),
        "LLMs": dict(category="AI/ML", prerequisites=["Transformers"], difficulty="advanced", demand_score=0.95,
                     resources=[{"title": "LLM Fundamentals", "type": "course", "hours": 20}],
                     projects=[{"title": "LLM Fine-tuning", "difficulty": "advanced"}]),
        "Prompt Engineering": dict(category="AI/ML", prerequisites=["LLMs"], difficulty="intermediate", demand_score=0.85,
                                    resources=[{"title": "Prompt Engineering Guide", "type": "course", "hours": 8}],
                                    projects=[{"title": "Prompt Optimization Project", "difficulty": "intermediate"}]),
        "Vector Databases": dict(category="AI/ML", prerequisites=["Python"], difficulty="intermediate", demand_score=0.8,
                                  resources=[{"title": "Vector DBs for AI", "type": "course", "hours": 10}],
                                  projects=[{"title": "Vector Search Implementation", "difficulty": "intermediate"}]),
        "RAG": dict(category="AI/ML", prerequisites=["LLMs", "Vector Databases"], difficulty="advanced", demand_score=0.9,
                    resources=[{"title": "RAG with LangChain", "type": "course", "hours": 15}],
                    projects=[{"title": "Document Q&A System", "difficulty": "advanced"}]),
        "Agentic AI": dict(category="AI/ML", prerequisites=["LLMs", "RAG"], difficulty="advanced", demand_score=0.9,
                            resources=[{"title": "Building AI Agents", "type": "course", "hours": 25}],
                            projects=[{"title": "AI Agent with Tools", "difficulty": "advanced"}]),
        "FastAPI": dict(category="Deployment", prerequisites=["Python"], difficulty="intermediate", demand_score=0.75,
                         resources=[{"title": "FastAPI Crash Course", "type": "course", "hours": 12}],
                         projects=[{"title": "REST API with FastAPI", "difficulty": "intermediate"}]),
        "Docker": dict(category="Deployment", prerequisites=[], difficulty="intermediate", demand_score=0.7,
                        resources=[{"title": "Docker for Beginners", "type": "course", "hours": 10}],
                        projects=[{"title": "Containerize an App", "difficulty": "intermediate"}]),
        "Cloud": dict(category="Deployment", prerequisites=["Docker"], difficulty="intermediate", demand_score=0.8,
                       resources=[{"title": "Cloud Deployment 101", "type": "course", "hours": 15}],
                       projects=[{"title": "Deploy ML Model to Cloud", "difficulty": "intermediate"}]),
        "MLOps": dict(category="Deployment", prerequisites=["Cloud", "Docker"], difficulty="advanced", demand_score=0.85,
                       resources=[{"title": "MLOps Fundamentals", "type": "course", "hours": 20}],
                       projects=[{"title": "End-to-End ML Pipeline", "difficulty": "advanced"}]),
    }
    return {name: SkillNode(name=name, **kwargs) for name, kwargs in raw.items()}


SKILL_GRAPH = build_skill_graph()
SKILL_VOCAB = list(SKILL_GRAPH.keys())

GOAL_SKILL_MAPPING = {
    "AI Engineer": {"required": ["Python", "Machine Learning", "Deep Learning", "Neural Networks", "FastAPI", "Docker", "MLOps"],
                    "recommended": ["Cloud", "Transformers"]},
    "Generative AI Engineer": {"required": ["Python", "Machine Learning", "Deep Learning", "Transformers", "LLMs", "RAG", "Vector Databases", "Prompt Engineering"],
                                "recommended": ["Agentic AI", "FastAPI"]},
    "Data Scientist": {"required": ["Python", "SQL", "Statistics", "Machine Learning"], "recommended": ["Deep Learning"]},
    "Backend Developer": {"required": ["Python", "FastAPI", "Docker"], "recommended": ["SQL", "Cloud"]},
    "Full Stack Developer": {"required": ["Python", "FastAPI"], "recommended": ["Docker", "Cloud"]},
    "Data Analyst": {"required": ["Python", "SQL", "Statistics"], "recommended": ["Machine Learning"]},
    "MLOps Engineer": {"required": ["Python", "Docker", "Cloud", "MLOps", "Machine Learning"], "recommended": ["FastAPI"]},
}

LEARNING_STYLE_RESOURCES = {
    "visual": [{"type": "video", "priority": 1.5}, {"type": "course", "priority": 1.2}, {"type": "article", "priority": 0.8}],
    "reading": [{"type": "article", "priority": 1.5}, {"type": "book", "priority": 1.3}, {"type": "course", "priority": 1.0}],
    "hands-on": [{"type": "project", "priority": 1.8}, {"type": "assessment", "priority": 1.3}, {"type": "course", "priority": 0.9}],
    "mixed": [{"type": "course", "priority": 1.3}, {"type": "video", "priority": 1.2}, {"type": "project", "priority": 1.2}, {"type": "article", "priority": 1.0}],
}

# ============================================================
# SERVICE: profile extraction  (Groq LLM, with heuristic fallback)
# ============================================================

class ProfileExtractionService:
    async def extract_profile(self, conversation: str) -> Dict:
        if HAS_KEY:
            try:
                return await self._extract_with_llm(conversation)
            except Exception as e:
                print(f"[ProfileExtraction] Groq call failed, falling back: {e}")
        return self._extract_heuristic(conversation)

    async def _extract_with_llm(self, text: str) -> Dict:
        goals = ", ".join(GOAL_SKILL_MAPPING.keys())
        skills = ", ".join(SKILL_VOCAB)
        system = f"""You extract a structured learner profile from a free-text message for a career-learning-path app.
Pick exactly one goal from this list (choose the closest match): {goals}.
Known skills must come only from this list: {skills}.
experience_level must be one of: beginner, intermediate, advanced.
learning_style must be one of: visual, reading, hands-on, mixed (default mixed if not stated).
Respond with ONLY raw JSON, no markdown fences:
{{"goal":"AI Engineer","experience_level":"beginner","weekly_hours":10,"deadline_months":6,"learning_style":"mixed","skills":{{"Python":0.6}},"interests":["genai"],"reply_to_user":"one warm sentence acknowledging their goal"}}
skills values are estimated proficiency 0.0-1.0 based only on what they explicitly claim to know. Keep reply_to_user under 30 words."""
        raw = await call_llm(system, text)
        parsed = json.loads(strip_fences(raw))
        if parsed.get("goal") not in GOAL_SKILL_MAPPING:
            parsed["goal"] = self._guess_goal(text)
        parsed.setdefault("weekly_hours", 10)
        parsed.setdefault("deadline_months", 6)
        parsed.setdefault("learning_style", "mixed")
        parsed.setdefault("skills", {})
        parsed.setdefault("interests", [])
        parsed["fallback"] = False
        return parsed

    def _guess_goal(self, text: str) -> str:
        low = text.lower()
        if "generative" in low or "genai" in low or "llm" in low:
            return "Generative AI Engineer"
        if "data scien" in low:
            return "Data Scientist"
        if "data analy" in low:
            return "Data Analyst"
        if "mlops" in low:
            return "MLOps Engineer"
        if "full stack" in low or "fullstack" in low:
            return "Full Stack Developer"
        if "backend" in low:
            return "Backend Developer"
        return "AI Engineer"

    def _extract_heuristic(self, conversation: str) -> Dict:
        text_lower = conversation.lower()
        profile = {"goal": None, "experience_level": "beginner", "skills": {}, "weekly_hours": 10,
                   "deadline_months": 6, "interests": [], "learning_style": "mixed", "fallback": True}

        # Check longer/more specific goal names first so "Generative AI Engineer"
        # wins over the substring "AI Engineer" when both are present.
        for goal in sorted(GOAL_SKILL_MAPPING.keys(), key=len, reverse=True):
            if goal.lower() in text_lower:
                profile["goal"] = goal
                break
        if not profile["goal"]:
            profile["goal"] = self._guess_goal(text_lower)

        if "advanced" in text_lower:
            profile["experience_level"] = "advanced"
        elif "intermediate" in text_lower or "some experience" in text_lower:
            profile["experience_level"] = "intermediate"

        hours_match = re.search(r"(\d{1,2})\s*(hours|hrs|hr)", text_lower)
        if hours_match:
            profile["weekly_hours"] = min(40, int(hours_match.group(1)))

        deadline_match = re.search(r"(\d{1,2})\s*months?", text_lower)
        if deadline_match:
            profile["deadline_months"] = int(deadline_match.group(1))

        for style in LEARNING_STYLE_RESOURCES:
            if style.replace("-", " ") in text_lower or style in text_lower:
                profile["learning_style"] = style
                break
        if "video" in text_lower:
            profile["learning_style"] = "visual"
        elif "project" in text_lower or "hands on" in text_lower or "hands-on" in text_lower:
            profile["learning_style"] = "hands-on"
        elif "read" in text_lower or "article" in text_lower:
            profile["learning_style"] = "reading"

        for skill in SKILL_VOCAB:
            if skill.lower() in text_lower:
                proficiency = 0.6
                if "know" in text_lower or "experienced" in text_lower:
                    proficiency = 0.8
                elif "basic" in text_lower:
                    proficiency = 0.4
                profile["skills"][skill] = proficiency
        profile["interests"] = list(profile["skills"].keys())[:4]
        profile["reply_to_user"] = f"Got it — building a {profile['goal']} path for you now."
        return profile


# ============================================================
# SERVICE: skill gap analysis
# ============================================================

class SkillGapService:
    def calculate_gaps(self, user_skills: Dict[str, float], goal: str) -> Dict:
        if goal not in GOAL_SKILL_MAPPING:
            raise ValueError(f"Unknown goal: {goal}")
        required_skills = GOAL_SKILL_MAPPING[goal]["required"]
        recommended_skills = GOAL_SKILL_MAPPING[goal]["recommended"]
        gaps, proficiency = [], {}

        for skill in required_skills:
            current = user_skills.get(skill, 0)
            proficiency[skill] = current
            if current < 0.7:
                gaps.append({"skill": skill, "current": current, "required": 0.7, "gap": 0.7 - current, "priority": "high"})
        for skill in recommended_skills:
            current = user_skills.get(skill, 0)
            proficiency[skill] = current
            if current < 0.5:
                gaps.append({"skill": skill, "current": current, "required": 0.5, "gap": 0.5 - current, "priority": "medium"})

        gaps.sort(key=lambda x: x["gap"], reverse=True)
        return {
            "gaps": gaps,
            "proficiency": proficiency,
            "gap_count": len(gaps),
            "completion_percentage": 1 - (len(gaps) / max(len(required_skills), 1)),
        }


# ============================================================
# SERVICE: recommendations
# ============================================================

class RecommendationService:
    def get_recommendations(self, skill_gaps: List[Dict], user_skills: Dict, learning_style: str) -> List[Dict]:
        recommendations = []
        style_priority = LEARNING_STYLE_RESOURCES.get(learning_style, LEARNING_STYLE_RESOURCES["mixed"])

        for gap in skill_gaps:
            skill_name = gap["skill"]
            node = SKILL_GRAPH.get(skill_name)
            if not node:
                continue

            resources = []
            for resource in node.resources:
                style_score = next((s["priority"] for s in style_priority if s["type"] == resource.get("type")), 1.0)
                difficulty_match = 1.0
                if node.difficulty == "beginner" and gap.get("current", 0) > 0.5:
                    difficulty_match = 0.7
                elif node.difficulty == "advanced" and gap.get("current", 0) < 0.2:
                    difficulty_match = 0.8
                total_score = style_score * 0.4 + difficulty_match * 0.3 + node.demand_score * 0.3
                resources.append({
                    "title": resource.get("title", f"{skill_name} Resource"),
                    "type": resource.get("type", "course"),
                    "hours": resource.get("hours", 10),
                    "score": round(total_score, 3),
                })
            resources.sort(key=lambda x: x["score"], reverse=True)

            projects = [{"title": p.get("title", f"{skill_name} Project"), "difficulty": p.get("difficulty", "intermediate")} for p in node.projects]

            recommendations.append({
                "skill": skill_name,
                "gap": round(gap["gap"], 3),
                "priority": gap["priority"],
                "demand_score": node.demand_score,
                "resources": resources[:3],
                "projects": projects[:2],
                "why": self._explain(skill_name, gap, node),
            })
        return recommendations

    def _explain(self, skill: str, gap: Dict, node: SkillNode) -> str:
        current, required = gap.get("current", 0), gap.get("required", 0.7)
        demand_note = f"It also carries a {round(node.demand_score * 100)}% market-demand score among roles like yours."
        if current == 0:
            base = f"You haven't learned {skill} yet. This is {'essential' if gap['priority'] == 'high' else 'a strong complement'} for your goal."
        else:
            base = f"You have partial knowledge of {skill} ({round(current * 100)}%), but reaching {round(required * 100)}% proficiency is needed for your goal."
        return f"{base} {demand_note}"


# ============================================================
# SERVICE: path generation
# ============================================================

class PathGenerator:
    def generate_path(self, user_id: str, profile: Dict, recommendations: List[Dict]) -> LearningPath:
        milestones, total_hours, phase = [], 0, 1
        recommendations = sorted(recommendations, key=lambda x: 0 if x["priority"] == "high" else 1)

        for rec in recommendations:
            node = SKILL_GRAPH.get(rec["skill"])
            resources = []
            for r in rec.get("resources", [])[:3]:
                resources.append(Resource(
                    id=f"res_{uuid.uuid4().hex[:8]}",
                    title=r.get("title", f"{rec['skill']} Resource"),
                    type=r.get("type", "course"),
                    skills=[rec["skill"]],
                    difficulty=node.difficulty if node else "beginner",
                    duration_hours=r.get("hours", 10),
                    prerequisites=node.prerequisites if node else [],
                    description=f"Learn {rec['skill']} for your {profile['goal']} goal",
                ))
                total_hours += r.get("hours", 10)

            project = {
                "title": rec.get("projects", [{}])[0].get("title", f"{rec['skill']} Project") if rec.get("projects") else f"{rec['skill']} Project",
                "description": f"Build a project to demonstrate {rec['skill']} skills",
                "difficulty": rec.get("projects", [{}])[0].get("difficulty", "intermediate") if rec.get("projects") else "intermediate",
            }
            assessment = {
                "title": f"{rec['skill']} Assessment",
                "questions": self._assessment_questions(rec["skill"]),
                "passing_score": 0.7,
            }

            milestones.append(Milestone(
                id=f"milestone_{uuid.uuid4().hex[:8]}",
                title=f"Phase {phase}: {rec['skill']}",
                phase=phase,
                skills=[rec["skill"]],
                resources=resources,
                project=project,
                assessment=assessment,
                estimated_hours=sum(r.get("hours", 10) for r in rec.get("resources", [])[:3]),
            ))
            phase += 1

        weeks_needed = total_hours / max(profile.get("weekly_hours", 10), 1)
        estimated_completion = datetime.now() + timedelta(days=int(weeks_needed * 7))
        return LearningPath(user_id=user_id, goal=profile["goal"], milestones=milestones,
                             total_hours=total_hours, estimated_completion=estimated_completion, current_phase=0)

    def _assessment_questions(self, skill: str) -> List[Dict]:
        return [
            {"question": f"What is the core concept of {skill}?", "options": ["Option A", "Option B", "Option C", "Option D"], "correct": 0},
            {"question": f"How would you apply {skill} in practice?", "options": ["Option A", "Option B", "Option C", "Option D"], "correct": 1},
        ]


# ============================================================
# SERVICE: assessment-driven adaptation
# (accelerate / reinforce / relearn — mutates the path in place)
# ============================================================

class AdaptationService:
    def adapt_path(self, path: LearningPath, milestone_id: str, score: float) -> Dict:
        target = next((m for m in path.milestones if m.id == milestone_id), None)
        if not target:
            return {"error": "Milestone not found"}

        target.completed = True
        target.score = score
        target.completed_at = datetime.now()
        target.last_reviewed_at = datetime.now()

        result = {"milestone": target.title, "score": score, "action": None, "message": None}

        if score >= 0.8:
            result["action"] = "accelerate"
            result["message"] = f"Great job! You've mastered {target.skills[0]}. Moving to advanced content."
            for i, m in enumerate(path.milestones):
                if m.id == milestone_id and i + 1 < len(path.milestones):
                    path.current_phase = i + 1
                    break

        elif score >= 0.5:
            result["action"] = "reinforce"
            result["message"] = "Good effort! Let's reinforce key concepts before moving on."
            practice = Milestone(
                id=f"practice_{uuid.uuid4().hex[:8]}",
                title=f"Practice: {target.skills[0]} Concepts",
                phase=target.phase, skills=target.skills,
                resources=[Resource(id=f"res_{uuid.uuid4().hex[:8]}", title=f"Practice Exercises for {target.skills[0]}",
                                     type="practice", skills=target.skills, difficulty="intermediate",
                                     duration_hours=5, prerequisites=target.skills,
                                     description="Reinforce your understanding with hands-on practice")],
                project={"title": "Practice Project", "description": "Apply what you've learned", "difficulty": "intermediate"},
                assessment={"title": "Re-assessment", "questions": [], "passing_score": 0.7},
                estimated_hours=5,
            )
            idx = next(i for i, m in enumerate(path.milestones) if m.id == milestone_id)
            path.milestones.insert(idx + 1, practice)

        else:
            result["action"] = "relearn"
            result["message"] = f"Let's build a stronger foundation before continuing with {target.skills[0]}."
            skill = target.skills[0]
            prereqs = SKILL_GRAPH[skill].prerequisites if skill in SKILL_GRAPH else []
            idx = next(i for i, m in enumerate(path.milestones) if m.id == milestone_id)
            for offset, prereq in enumerate(prereqs):
                review = Milestone(
                    id=f"prereq_{uuid.uuid4().hex[:8]}",
                    title=f"Review: {prereq}",
                    phase=target.phase, skills=[prereq],
                    resources=[Resource(id=f"res_{uuid.uuid4().hex[:8]}", title=f"{prereq} Fundamentals",
                                         type="course", skills=[prereq], difficulty="beginner",
                                         duration_hours=8, prerequisites=[], description=f"Build foundation in {prereq}")],
                    project={"title": f"{prereq} Practice", "description": "Reinforce understanding", "difficulty": "beginner"},
                    assessment={"title": f"{prereq} Check", "questions": [], "passing_score": 0.7},
                    estimated_hours=8,
                )
                path.milestones.insert(idx + offset, review)

        path.updated_at = datetime.now()
        return result


# ============================================================
# SERVICE: what-if simulator
# (goal switch / weekly-hours change — kept — PLUS a graph-based
# "skip this skill" downstream-impact check, merged in)
# ============================================================

class WhatIfService:
    def simulate_change(self, path: LearningPath, change_type: str, new_value: Any, baseline_hours: int = 10) -> Dict:
        if change_type == "goal":
            return self._simulate_goal_change(path, new_value, baseline_hours)
        if change_type == "weekly_hours":
            return self._simulate_time_change(path, new_value, baseline_hours)
        if change_type == "skip_skill":
            return self._simulate_skip_skill(path, new_value)
        return {"error": "Unknown change type"}

    def _simulate_goal_change(self, path: LearningPath, new_goal: str, baseline_hours: int) -> Dict:
        if new_goal not in GOAL_SKILL_MAPPING:
            return {"error": f"Unknown goal: {new_goal}"}
        new_required = GOAL_SKILL_MAPPING[new_goal]["required"]
        old_required = GOAL_SKILL_MAPPING[path.goal]["required"]
        added = [s for s in new_required if s not in old_required]
        removed = [s for s in old_required if s not in new_required]
        total_hours = sum(r.get("hours", 10) for s in new_required if s in SKILL_GRAPH for r in SKILL_GRAPH[s].resources)
        weeks_needed = total_hours / max(baseline_hours, 1)
        new_timeline = datetime.now() + timedelta(days=int(weeks_needed * 7))
        return {
            "current_goal": path.goal, "new_goal": new_goal, "added_skills": added, "removed_skills": removed,
            "new_timeline": new_timeline.isoformat(), "total_hours": total_hours,
            "message": f"Switching to {new_goal} would add {len(added)} new skill(s) and drop {len(removed)} you no longer need.",
        }

    def _simulate_time_change(self, path: LearningPath, new_hours: int, baseline_hours: int) -> Dict:
        total_hours = path.total_hours
        current_weeks = total_hours / max(baseline_hours, 1)
        new_weeks = total_hours / max(new_hours, 1)
        current_date = datetime.now() + timedelta(days=int(current_weeks * 7))
        new_date = datetime.now() + timedelta(days=int(new_weeks * 7))
        return {
            "current_weekly_hours": baseline_hours, "new_weekly_hours": new_hours,
            "current_completion": current_date.isoformat(),
            "new_completion": new_date.isoformat(), "months_difference": round(abs(current_weeks - new_weeks) / 4, 1),
            "message": f"At {new_hours} hrs/week you'd finish in about {round(new_weeks)} weeks instead of {round(current_weeks)}.",
        }

    def _simulate_skip_skill(self, path: LearningPath, skill: str) -> Dict:
        """Graph-based check: what becomes unreachable if this skill is skipped."""
        if skill not in SKILL_GRAPH:
            return {"error": f"Unknown skill: {skill}"}
        remaining_skills = {m.skills[0] for m in path.milestones if not m.completed and m.skills}
        blocked = []
        for candidate in remaining_skills:
            if candidate == skill:
                continue
            if self._depends_on(candidate, skill, set()):
                blocked.append(candidate)
        verdict = (
            "Skipping this wouldn't block anything else currently on your path — relatively safe to defer."
            if not blocked
            else f"Skipping this would block {len(blocked)} downstream skill(s): {', '.join(blocked)}."
        )
        return {"skill": skill, "blocked_skills": blocked, "blocked_count": len(blocked), "verdict": verdict}

    def _depends_on(self, skill: str, target: str, seen: set) -> bool:
        if skill in seen or skill not in SKILL_GRAPH:
            return False
        seen.add(skill)
        node = SKILL_GRAPH[skill]
        if target in node.prerequisites:
            return True
        return any(self._depends_on(p, target, seen) for p in node.prerequisites)


# ============================================================
# SERVICE: AI coach  (Groq LLM, with rule-based fallback)
# ============================================================

class CoachingService:
    async def get_coaching_response(self, query: str, context: Dict) -> str:
        if HAS_KEY:
            try:
                return await self._respond_with_llm(query, context)
            except Exception as e:
                print(f"[Coaching] Groq call failed, falling back: {e}")
        return self._respond_heuristic(query, context)

    async def _respond_with_llm(self, query: str, context: Dict) -> str:
        system = f"""You are Saarthi, a friendly AI learning-path coach embedded in a career roadmap app.
Learner: goal={context['goal']}, experience={context['experience']}, weekly_hours={context['weekly_hours']}, learning_style={context['learning_style']}.
Progress: {context['completed']}/{context['total']} milestones complete. Pacing status: {context['pacing_status']}.
Current/next milestone: {context['next_milestone']}.
Answer the learner's question in under 80 words, warm and concrete, grounded only in the info above — never invent skills or milestones that weren't mentioned."""
        return await call_llm(system, query, max_tokens=400)

    def _respond_heuristic(self, query: str, context: Dict) -> str:
        q = query.lower()
        if "why" in q and "learn" in q:
            skill = next((s for s in SKILL_VOCAB if s.lower() in q), None)
            if skill and skill in SKILL_GRAPH:
                required = GOAL_SKILL_MAPPING.get(context["goal"], {}).get("required", [])
                essential = "essential" if skill in required else "recommended"
                return (f"You're learning {skill} because it's {essential} for becoming a {context['goal']}. "
                        f"It carries a {round(SKILL_GRAPH[skill].demand_score * 100)}% market-demand score.")
            return "Each skill on your path is selected because it's required (or strongly recommended) for your specific goal."
        if "skip" in q:
            return "I'd only skip a skill if you're confident in it already — try the readiness check first, or ask me 'what if I skip X' to see what it would block."
        if "progress" in q:
            return f"You've completed {context['completed']} of {context['total']} milestones. {context['pacing_status']}"
        if "behind" in q or "pace" in q or "late" in q:
            return context["pacing_status"]
        return "I'm here to help with your path — ask me why a skill is included, how you're pacing, or what a change would cost you. (Offline mode: connect ANTHROPIC_API_KEY for richer answers.)"


# ============================================================
# SERVICE: job description reverse-engineering (Groq LLM + fallback)
# ============================================================

class JobDescriptionService:
    async def analyze(self, job_text: str) -> Dict:
        if HAS_KEY:
            try:
                skills_found = await self._extract_with_llm(job_text)
            except Exception as e:
                print(f"[JobDescription] Groq call failed, falling back: {e}")
                skills_found = self._extract_heuristic(job_text)
        else:
            skills_found = self._extract_heuristic(job_text)

        if not skills_found:
            skills_found = ["Python", "Machine Learning", "SQL"]

        path_order = self._order_with_prereqs(skills_found)
        return {
            "skills_found": skills_found,
            "recommended_learning_order": path_order,
            "custom_goal_label": f"Job-Ready {'/'.join(skills_found[:3])} Track",
        }

    async def _extract_with_llm(self, job_text: str) -> List[str]:
        system = f"""Extract the technical skills mentioned or clearly implied in this job description.
Only use skills from this exact vocabulary: {', '.join(SKILL_VOCAB)}.
Respond with ONLY a raw JSON array of matching skill names, e.g. ["Python","SQL"]. No commentary."""
        raw = await call_llm(system, job_text, max_tokens=300)
        parsed = json.loads(strip_fences(raw))
        return [s for s in parsed if s in SKILL_GRAPH]

    def _extract_heuristic(self, job_text: str) -> List[str]:
        low = job_text.lower()
        return [skill for skill in SKILL_VOCAB if skill.lower() in low]

    def _order_with_prereqs(self, skills: List[str]) -> List[str]:
        ordered = []
        def add(skill):
            if skill in ordered or skill not in SKILL_GRAPH:
                return
            for prereq in SKILL_GRAPH[skill].prerequisites:
                add(prereq)
            ordered.append(skill)
        for s in skills:
            add(s)
        return ordered


# ============================================================
# SERVICE: benchmarking, pacing risk, spaced repetition
# (innovations layered on top of the original design)
# ============================================================

class InsightsService:
    def __init__(self):
        self._cohort_seeded = False
        self.cohort: List[Dict] = []  # [{goal, completed_count, created_days_ago}]

    def seed_cohort(self, n=150):
        if self._cohort_seeded:
            return
        goals = list(GOAL_SKILL_MAPPING.keys())
        for _ in range(n):
            goal = random.choice(goals)
            tenure_days = random.randint(5, 220)
            weekly_hours = random.randint(3, 15)
            pace_per_week = max(0.15, weekly_hours / 14 + (random.random() - 0.5) * 0.15)
            required_count = len(GOAL_SKILL_MAPPING[goal]["required"])
            completed = min(required_count, round((tenure_days / 7) * pace_per_week))
            self.cohort.append({"goal": goal, "completed_count": completed, "tenure_days": tenure_days})
        self._cohort_seeded = True

    def cohort_percentile(self, goal: str, my_completed: int) -> Optional[Dict]:
        peers = [c for c in self.cohort if c["goal"] == goal]
        if not peers:
            return None
        below = len([c for c in peers if c["completed_count"] <= my_completed])
        percentile = round((below / len(peers)) * 100)
        return {"goal": goal, "percentile": percentile, "cohort_size": len(peers), "my_completed": my_completed}

    def pacing_risk(self, user: UserProfile, path: Optional[LearningPath]) -> Dict:
        elapsed_weeks = max(0.2, (datetime.now() - user.created_at).total_seconds() / (7 * 86400))
        if not path:
            return {"status": "new", "message": "No path yet — pacing kicks in once your roadmap is generated."}
        hours_done = sum(m.estimated_hours for m in path.milestones if m.completed)
        expected_hours = elapsed_weeks * user.weekly_hours
        ratio = hours_done / expected_hours if expected_hours > 0 else 1.0

        if hours_done == 0 and elapsed_weeks < 1:
            return {"status": "new", "message": "Just getting started — no pacing signal yet.", "ratio": 0}
        if ratio >= 0.85:
            return {"status": "on_pace", "message": "You're on pace with the hours you committed. Nice consistency.", "ratio": round(ratio, 2)}
        if ratio >= 0.5:
            return {"status": "slightly_behind", "message": "You're a bit behind your committed pace — consider a lighter next milestone this week.", "ratio": round(ratio, 2)}
        return {"status": "behind", "message": "You're notably behind your committed weekly hours. Want to lower your weekly-hours target so the plan stays realistic?", "ratio": round(ratio, 2)}

    def reviews_due(self, path: Optional[LearningPath], interval_days: int = 21) -> List[Dict]:
        if not path:
            return []
        now = datetime.now()
        due = []
        for m in path.milestones:
            if not m.completed or not m.last_reviewed_at:
                continue
            days_since = (now - m.last_reviewed_at).days
            if days_since >= interval_days:
                due.append({"milestone_id": m.id, "title": m.title, "skill": m.skills[0] if m.skills else "", "days_since": days_since})
        return sorted(due, key=lambda x: -x["days_since"])[:5]


INSIGHTS = InsightsService()
INSIGHTS.seed_cohort()

# ============================================================
# SERVICE INSTANCES
# ============================================================

profile_service = ProfileExtractionService()
gap_service = SkillGapService()
rec_service = RecommendationService()
path_generator = PathGenerator()
adapt_service = AdaptationService()
whatif_service = WhatIfService()
coach_service = CoachingService()
job_service = JobDescriptionService()


def build_path_for_user(user: UserProfile) -> LearningPath:
    gaps = gap_service.calculate_gaps(user.skills, user.goal)
    recs = rec_service.get_recommendations(gaps["gaps"], user.skills, user.learning_style)
    path = path_generator.generate_path(user.id, user.model_dump(), recs)
    DB.save_path(path)
    return path


# ============================================================
# API — ONBOARDING & PROFILE
# ============================================================

@app.get("/api/health")
async def health():
    return {"ok": True, "using_live_ai": HAS_KEY}


@app.post("/api/onboarding")
async def onboarding(conversation: Dict):
    text = conversation.get("text", "")
    profile_data = await profile_service.extract_profile(text)

    user_id = f"user_{uuid.uuid4().hex[:8]}"
    profile = UserProfile(
        id=user_id, name=conversation.get("name", "Learner"), goal=profile_data["goal"],
        experience_level=profile_data["experience_level"], weekly_hours=profile_data["weekly_hours"],
        deadline_months=profile_data["deadline_months"], learning_style=profile_data.get("learning_style", "mixed"),
        skills=profile_data.get("skills", {}), interests=profile_data.get("interests", []),
    )
    DB.save_user(profile)
    DB.chat_history[user_id] = [
        {"role": "user", "content": text},
        {"role": "bot", "content": profile_data.get("reply_to_user", f"Welcome! Building your {profile.goal} path now.")},
    ]

    return {
        "user_id": user_id,
        "profile": profile.model_dump(),
        "message": profile_data.get("reply_to_user", f"Welcome! I've set up your profile to become a {profile.goal}."),
        "using_live_ai": HAS_KEY,
    }


@app.get("/api/learners/{user_id}")
async def get_learner(user_id: str):
    user = DB.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"profile": user.model_dump(), "messages": DB.chat_history.get(user_id, []), "has_profile": True}


# ============================================================
# API — SINGLE CONVERSATIONAL ENDPOINT
# (routes to onboarding on first message, coaching afterwards —
# convenience wrapper around the granular endpoints below)
# ============================================================

@app.post("/api/chat")
async def chat(body: Dict):
    user_id = body.get("user_id")
    message = body.get("message", "")

    if not user_id or not DB.get_user(user_id):
        onboard_result = await onboarding({"text": message})
        user_id = onboard_result["user_id"]
        build_path_for_user(DB.get_user(user_id))
        return {
            "user_id": user_id,
            "reply": onboard_result["message"],
            "dashboard": await _dashboard_payload(user_id),
            "using_live_ai": HAS_KEY,
        }

    DB.chat_history.setdefault(user_id, []).append({"role": "user", "content": message})
    user = DB.get_user(user_id)
    path = DB.get_path(user_id)

    if re.search(r"\b(also|switch|instead|change goal|new goal|pivot)\b", message.lower()):
        parsed = await profile_service.extract_profile(message)
        if parsed.get("goal") and parsed["goal"] != user.goal:
            user.goal = parsed["goal"]
            user.skills.update(parsed.get("skills", {}))
            user.updated_at = datetime.now()
            DB.save_user(user)
            path = build_path_for_user(user)
            reply = f"Updated your goal to {user.goal} and rebuilt your path."
            DB.chat_history[user_id].append({"role": "bot", "content": reply})
            return {"user_id": user_id, "reply": reply, "dashboard": await _dashboard_payload(user_id), "using_live_ai": HAS_KEY}

    next_milestone = next((m.title for m in path.milestones if not m.completed), "none — path complete") if path else "no path yet"
    pacing = INSIGHTS.pacing_risk(user, path)
    context = {
        "goal": user.goal, "experience": user.experience_level, "weekly_hours": user.weekly_hours,
        "learning_style": user.learning_style,
        "completed": len([m for m in path.milestones if m.completed]) if path else 0,
        "total": len(path.milestones) if path else 0,
        "pacing_status": pacing["message"], "next_milestone": next_milestone,
    }
    reply = await coach_service.get_coaching_response(message, context)
    DB.chat_history[user_id].append({"role": "bot", "content": reply})
    return {"user_id": user_id, "reply": reply, "dashboard": await _dashboard_payload(user_id), "using_live_ai": HAS_KEY}


# ============================================================
# API — GRANULAR ENDPOINTS (kept from the original design)
# ============================================================

@app.post("/api/skill-gap/{user_id}")
async def analyze_skill_gap(user_id: str):
    user = DB.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    result = gap_service.calculate_gaps(user.skills, user.goal)
    # Key names below (skill_gaps / completion) match what the frontend reads.
    return {
        "user_id": user_id,
        "goal": user.goal,
        "skill_gaps": result["gaps"],
        "proficiency": result["proficiency"],
        "gap_count": result["gap_count"],
        "completion": result["completion_percentage"],
    }


@app.post("/api/recommendations/{user_id}")
async def get_recommendations(user_id: str):
    user = DB.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    gaps = gap_service.calculate_gaps(user.skills, user.goal)
    recs = rec_service.get_recommendations(gaps["gaps"], user.skills, user.learning_style)
    return {"user_id": user_id, "goal": user.goal, "recommendations": recs, "total_gaps": len(recs)}


@app.post("/api/learning-path/{user_id}")
async def generate_learning_path(user_id: str):
    user = DB.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    path = build_path_for_user(user)
    return {
        "user_id": user_id, "goal": path.goal, "milestones": [m.model_dump() for m in path.milestones],
        "total_hours": path.total_hours, "estimated_completion": path.estimated_completion.isoformat(),
        "total_milestones": len(path.milestones),
    }


@app.post("/api/assessment/{user_id}/{milestone_id}")
async def submit_assessment(user_id: str, milestone_id: str, submission: Dict):
    user = DB.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    path = DB.get_path(user_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")

    score = submission.get("score")
    if score is None:
        score = round(random.uniform(0.5, 0.95), 2)  # demo-mode simulated score

    result = adapt_service.adapt_path(path, milestone_id, score)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    for m in path.milestones:
        if m.id == milestone_id:
            for skill in m.skills:
                user.skills[skill] = min(1.0, user.skills.get(skill, 0) + score * 0.3)
            break
    user.updated_at = datetime.now()
    DB.save_user(user)
    DB.save_path(path)

    return {
        "user_id": user_id, "milestone_id": milestone_id, "score": score,
        "action": result.get("action"), "message": result.get("message"),
        "updated_milestones": [m.model_dump() for m in path.milestones],
    }


@app.post("/api/what-if/{user_id}")
async def simulate_change(user_id: str, simulation: Dict):
    user = DB.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    path = DB.get_path(user_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")
    result = whatif_service.simulate_change(path, simulation.get("change_type"), simulation.get("new_value"), user.weekly_hours)
    return {"user_id": user_id, "simulation": result}


@app.post("/api/coach/{user_id}")
async def coaching(user_id: str, query: Dict):
    user = DB.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    path = DB.get_path(user_id)
    pacing = INSIGHTS.pacing_risk(user, path)
    next_milestone = next((m.title for m in path.milestones if not m.completed), "none — path complete") if path else "no path yet"
    context = {
        "goal": user.goal, "experience": user.experience_level, "weekly_hours": user.weekly_hours,
        "learning_style": user.learning_style,
        "completed": len([m for m in path.milestones if m.completed]) if path else 0,
        "total": len(path.milestones) if path else 0,
        "pacing_status": pacing["message"], "next_milestone": next_milestone,
    }
    reply = await coach_service.get_coaching_response(query.get("text", ""), context)
    return {"user_id": user_id, "query": query.get("text"), "response": reply, "using_live_ai": HAS_KEY}


@app.post("/api/job-analysis")
async def analyze_job(job_data: Dict):
    result = await job_service.analyze(job_data.get("text", ""))
    # gap_analysis / custom_goal are the keys the frontend reads; the newer
    # names (recommended_learning_order / custom_goal_label) are kept too.
    return {
        "skills_found": result["skills_found"],
        "recommended_learning_order": result["recommended_learning_order"],
        "gap_analysis": {"recommended_skills": result["recommended_learning_order"], "additional_skills": []},
        "custom_goal": result["custom_goal_label"],
        "custom_goal_label": result["custom_goal_label"],
        "using_live_ai": HAS_KEY,
    }


@app.post("/api/learning-style/{user_id}")
async def update_learning_style(user_id: str, style_data: Dict):
    user = DB.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_style = style_data.get("learning_style", "mixed")
    if new_style not in LEARNING_STYLE_RESOURCES:
        raise HTTPException(status_code=400, detail="Invalid learning style")
    user.learning_style = new_style
    user.updated_at = datetime.now()
    DB.save_user(user)
    return {"user_id": user_id, "learning_style": new_style, "message": f"Learning style updated to {new_style}"}


# ============================================================
# API — DASHBOARD (merges original progress view + the three
# added insight features: cohort percentile, pacing, reviews due)
# ============================================================

async def _dashboard_payload(user_id: str) -> Dict:
    user = DB.get_user(user_id)
    if not user:
        return None
    path = DB.get_path(user_id)

    total_milestones = len(path.milestones) if path else 0
    completed_milestones = len([m for m in path.milestones if m.completed]) if path else 0
    progress = completed_milestones / max(total_milestones, 1) if path else 0

    next_action = None
    if path:
        nxt = next((m for m in path.milestones if not m.completed), None)
        if nxt:
            next_action = {"id": nxt.id, "title": nxt.title, "skills": nxt.skills, "estimated_hours": nxt.estimated_hours}

    skill_map = {skill: user.skills.get(skill, 0) for skill in GOAL_SKILL_MAPPING.get(user.goal, {}).get("required", [])}

    return {
        "user_id": user_id,
        "goal": user.goal,
        "experience": user.experience_level,
        "learning_style": user.learning_style,
        "weekly_hours": user.weekly_hours,
        "progress_percentage": round(progress * 100, 1),
        "completed_milestones": completed_milestones,
        "total_milestones": total_milestones,
        "skill_map": skill_map,
        "next_action": next_action,
        "estimated_completion": path.estimated_completion.isoformat() if path else None,
        "milestones": [m.model_dump() for m in path.milestones] if path else [],
        "pacing": INSIGHTS.pacing_risk(user, path),
        "reviews_due": INSIGHTS.reviews_due(path),
        "cohort": INSIGHTS.cohort_percentile(user.goal, completed_milestones),
    }


@app.get("/api/dashboard/{user_id}")
async def get_dashboard(user_id: str):
    payload = await _dashboard_payload(user_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="User not found")
    return payload


@app.post("/api/review/{user_id}/{milestone_id}")
async def mark_reviewed(user_id: str, milestone_id: str):
    path = DB.get_path(user_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")
    m = next((m for m in path.milestones if m.id == milestone_id), None)
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found")
    m.last_reviewed_at = datetime.now()
    DB.save_path(path)
    return await _dashboard_payload(user_id)


# ============================================================
# API — DEMO DATA GENERATOR
# ============================================================

@app.post("/api/demo/create-user")
async def create_demo_user():
    onboard_result = await onboarding({
        "text": "I want to become a Generative AI Engineer in 4 months. I know Python, basic machine learning, "
                "and have built a few ML projects. I can dedicate 15 hours per week and prefer hands-on learning."
    })
    user_id = onboard_result["user_id"]
    path = build_path_for_user(DB.get_user(user_id))
    return {
        "user_id": user_id,
        "message": "Demo user created successfully!",
        "profile": onboard_result["profile"],
        "path_preview": {"goal": path.goal, "total_hours": path.total_hours, "milestone_count": len(path.milestones)},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
