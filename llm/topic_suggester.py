"""
Topic suggestion engine for the English Coach Agent.
Analyzes error patterns and generates personalized study topic recommendations.
Delivers suggestions naturally through conversation.
"""

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from config.settings import DB_PATH, RECENT_ERRORS_SESSIONS
from config.logging_config import setup_logging
from memory.database import DatabaseManager, get_db

logger = setup_logging()


@dataclass
class TopicSuggestion:
    topic: str
    reason: str
    error_category: str
    priority: str = "medium"  # high, medium, low
    examples: list[str] = field(default_factory=list)
    suggested_at: str = ""


class TopicSuggester:
    """
    Analyzes user errors to recommend personalized study topics.
    Tracks which suggestions have been given to avoid repetition.
    """

    # Topic mapping: error category → study suggestions
    TOPIC_MAP = {
        "tense": [
            {
                "topic": "Past Simple vs Present Perfect",
                "reason": "You've been mixing up past simple and present perfect. "
                         "These tenses have different uses in English.",
                "examples": [
                    "I have visited London last year → I visited London last year",
                    "I seen that movie → I've seen that movie",
                ],
            },
            {
                "topic": "Using the Past Continuous naturally",
                "reason": "Your past continuous usage could be more natural. "
                         "This tense helps describe background actions in stories.",
                "examples": [
                    "I was working when you called",
                    "It was raining when I left the house",
                ],
            },
            {
                "topic": "Future forms: will vs going to",
                "reason": "Understanding when to use 'will' vs 'going to' "
                         "makes your speech sound more natural.",
                "examples": [
                    "I'm going to visit my parents this weekend (plan)",
                    "I'll help you with that (spontaneous offer)",
                ],
            },
        ],
        "preposition": [
            {
                "topic": "Prepositions of time: in, on, at",
                "reason": "Prepositions of time are a common challenge. "
                         "The rules are simple once you know them.",
                "examples": [
                    "in June / in 2026 (months, years)",
                    "on Monday / on May 11th (days, dates)",
                    "at 3pm / at night (specific times)",
                ],
            },
            {
                "topic": "Prepositions of place: in, on, at",
                "reason": "Using the right preposition for location "
                         "can change the meaning completely.",
                "examples": [
                    "at the office (specific point)",
                    "in the city (enclosed area)",
                    "on the table (surface)",
                ],
            },
        ],
        "article": [
            {
                "topic": "When to use a/an/the in English",
                "reason": "Articles are tricky for Spanish speakers since "
                         "the rules differ between the two languages.",
                "examples": [
                    "a computer (any computer, first mention)",
                    "the computer (specific one we both know)",
                    "Computers are useful (general statement, no article)",
                ],
            },
        ],
        "word_order": [
            {
                "topic": "English sentence word order",
                "reason": "English follows a strict Subject-Verb-Object order. "
                         "Getting this right makes a big difference in clarity.",
                "examples": [
                    "I like very much coffee → I like coffee very much",
                    "She always is late → She is always late",
                ],
            },
        ],
        "subject_verb_agreement": [
            {
                "topic": "Subject-Verb agreement rules",
                "reason": "Making subjects and verbs agree is fundamental "
                         "for clear, correct English.",
                "examples": [
                    "He go to work → He goes to work",
                    "The people is happy → The people are happy",
                ],
            },
        ],
        "pronoun": [
            {
                "topic": "Pronoun usage and clarity",
                "reason": "Clear pronoun reference avoids confusion about "
                         "who or what you're talking about.",
                "examples": [
                    "My sister called her friend → My sister called my friend",
                    "It's your? → Is it yours?",
                ],
            },
        ],
        "modal": [
            {
                "topic": "Modal verbs: should, could, would, might",
                "reason": "Modal verbs add nuance and politeness to your English. "
                         "Each one has a specific use case.",
                "examples": [
                    "You should try this (advice)",
                    "Could you help me? (polite request)",
                    "I would go if I had time (hypothetical)",
                ],
            },
        ],
        "conditional": [
            {
                "topic": "Conditional sentences (if-clauses)",
                "reason": "Conditionals help you express possibilities, "
                         "hypotheticals, and regrets naturally.",
                "examples": [
                    "If it rains, I'll stay home (first conditional)",
                    "If I were you, I'd study more (second conditional)",
                ],
            },
        ],
        "plural": [
            {
                "topic": "Countable vs uncountable nouns",
                "reason": "Knowing which nouns can be counted affects "
                         "articles, quantifiers, and verb agreement.",
                "examples": [
                    "I need an advice → I need some advice",
                    "I have many informations → I have a lot of information",
                ],
            },
        ],
        "vocabulary": [
            {
                "topic": "Expanding your professional vocabulary",
                "reason": "Building on your technical vocabulary can help "
                         "you express ideas more precisely at work.",
                "examples": [],
            },
        ],
    }

    # Conversation templates for natural suggestion delivery
    DELIVERY_TEMPLATES = [
        "By the way, {name}, I've noticed something. {reason} Would you like to practice {topic} for a few minutes?",
        "Hey {name}, can I suggest something? {reason} It might be worth reviewing {topic} — want to give it a try?",
        "I've been keeping track, and I think {topic} could be really helpful for you. {reason} Interested?",
        "Quick thought — {reason}. If you're up for it, we could do a quick practice on {topic}.",
        "{name}, I've got a suggestion based on our conversations: {topic}. {reason} Want to explore that?",
    ]

    def __init__(self, db_path: str | None = None):
        self._db: DatabaseManager | None = None
        self._db_path = db_path or str(DB_PATH)
        self._profile_cache: dict | None = None

    async def initialize(self):
        self._db = await get_db()

    @property
    def db(self) -> DatabaseManager:
        if self._db is None:
            raise RuntimeError(
                "TopicSuggester not initialized. Call initialize() first."
            )
        return self._db

    async def analyze_and_suggest(
        self,
        threshold: int = 3,
        recent_sessions: int = 3,
        max_suggestions: int = 1,
    ) -> list[TopicSuggestion]:
        """
        Analyze recent errors and generate topic suggestions.
        Only suggests if error count exceeds threshold.

        Args:
            threshold: Minimum errors of same type to trigger suggestion
            recent_sessions: Number of recent sessions to analyze
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of TopicSuggestion objects
        """
        # Get frequent errors from recent sessions
        rows = await self.db.fetch_all(
            """
            SELECT error_category, COUNT(*) as count
            FROM corrections
            WHERE session_id IN (
                SELECT id FROM sessions
                ORDER BY started_at DESC
                LIMIT ?
            )
            GROUP BY error_category
            ORDER BY count DESC
            """,
            (recent_sessions,),
        )

        suggestions = []

        for row in rows:
            category = row["error_category"] or "grammar"
            count = row["count"]

            if count < threshold:
                continue

            # Check which topics we've already suggested recently
            already_suggested = await self._get_recently_suggested(category)

            # Pick available topics for this category
            topics = self.TOPIC_MAP.get(category, [])
            available = [t for t in topics if t["topic"] not in already_suggested]

            if not available:
                # All topics suggested recently — check if enough time has passed
                logger.debug(f"No new topics for category '{category}'")
                continue

            # Pick the best topic (first available)
            topic_data = available[0]

            priority = "high" if count >= threshold * 2 else "medium"

            suggestion = TopicSuggestion(
                topic=topic_data["topic"],
                reason=topic_data["reason"],
                error_category=category,
                priority=priority,
                examples=topic_data.get("examples", []),
            )
            suggestions.append(suggestion)

            if len(suggestions) >= max_suggestions:
                break

        return suggestions

    async def record_suggestion(self, suggestion: TopicSuggestion):
        """Record that a topic was suggested (for anti-repetition)."""
        await self.db.insert(
            "topic_suggestions",
            {
                "topic": suggestion.topic,
                "reason": suggestion.reason,
                "error_category_reference": suggestion.error_category,
                "reviewed": 0,
            },
        )

    async def mark_as_reviewed(self, topic: str):
        """Mark a topic suggestion as reviewed by the user."""
        await self.db.execute(
            """
            UPDATE topic_suggestions
            SET reviewed = 1
            WHERE topic = ? AND reviewed = 0
            """,
            (topic,),
        )

    async def _get_recently_suggested(
        self, category: str, days: int = 7
    ) -> set[str]:
        """Get topics recently suggested for a category to avoid repetition."""
        rows = await self.db.fetch_all(
            """
            SELECT DISTINCT topic
            FROM topic_suggestions
            WHERE error_category_reference = ?
              AND suggested_at >= datetime('now', ?)
            """,
            (category, f"-{days} days"),
        )

        return {row["topic"] for row in rows}

    async def get_recently_suggested_all(
        self, days: int = 7
    ) -> list[dict]:
        """Get all topic suggestions made in recent days."""
        return await self.db.fetch_all(
            """
            SELECT topic, error_category_reference, suggested_at, reviewed
            FROM topic_suggestions
            WHERE suggested_at >= datetime('now', ?)
            ORDER BY suggested_at DESC
            """,
            (f"-{days} days",),
        )

    async def get_pending_suggestions(self) -> list[dict]:
        """Get suggestions that haven't been reviewed yet."""
        return await self.db.fetch_all(
            """
            SELECT * FROM topic_suggestions
            WHERE reviewed = 0
            ORDER BY suggested_at DESC
            """
        )

    async def generate_delivery_text(
        self, suggestion: TopicSuggestion, user_name: str = "there"
    ) -> str:
        """
        Generate a natural-sounding conversation opener for a topic suggestion.
        """
        template = random.choice(self.DELIVERY_TEMPLATES)

        text = template.format(
            name=user_name,
            reason=suggestion.reason,
            topic=suggestion.topic,
        )

        return text

    async def should_suggest_now(self) -> bool:
        """
        Determine if it's a good time to deliver a suggestion.
        Checks: enough errors accumulated, not recently suggested.
        """
        # Check if we have any pending suggestions
        pending = await self.get_pending_suggestions()
        if pending:
            return True

        # Check if enough errors have accumulated
        recent_count = await self.db.fetch_one(
            """
            SELECT COUNT(*) as cnt FROM corrections
            WHERE timestamp >= datetime('now', '-3 days')
            """
        )

        return (recent_count["cnt"] if recent_count else 0) >= 3

    async def get_suggested_study_plan(self) -> list[dict]:
        """
        Generate a study plan based on error patterns.
        Returns topics ordered by priority.
        """
        # Get errors by category for last 30 days
        rows = await self.db.fetch_all(
            """
            SELECT error_category, COUNT(*) as count
            FROM corrections
            WHERE timestamp >= datetime('now', '-30 days')
              AND error_category IS NOT NULL
              AND error_category != ''
            GROUP BY error_category
            ORDER BY count DESC
            """
        )

        plan = []

        for row in rows:
            category = row["error_category"]
            count = row["count"]

            # Get available topic for this category
            topics = self.TOPIC_MAP.get(category, [])
            if topics:
                plan.append({
                    "category": category,
                    "count": count,
                    "suggested_topic": topics[0]["topic"],
                    "reason": topics[0]["reason"],
                    "priority": "high" if count >= 5 else "medium" if count >= 3 else "low",
                })

        return plan

    @staticmethod
    def get_all_categories() -> list[str]:
        """Return all known error categories."""
        return list(TopicSuggester.TOPIC_MAP.keys())
