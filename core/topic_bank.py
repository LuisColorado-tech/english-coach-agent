"""
Intelligent topic bank for spontaneous conversation openings.
Selects relevant, varied topics based on user profile, recent history,
time of day, and grammar practice needs.
"""

import random
from collections import deque
from datetime import datetime
from typing import Optional

from config.logging_config import setup_logging

logger = setup_logging()


class TopicBank:
    """
    Maintains a curated set of conversation topics for spontaneous triggers.
    Selects topics avoiding repetition and matching user context.
    """

    # Max entries in the recently-used queue
    MAX_RECENT = 15

    # General conversation starters by time of day
    TIME_TOPICS = {
        "morning": [
            "morning routines and habits",
            "plans for the day ahead",
            "breakfast traditions around the world",
            "morning productivity tips",
            "how you slept and dreams",
            "weekend plans and aspirations",
        ],
        "afternoon": [
            "how the day is going so far",
            "lunch and food preferences",
            "work projects and challenges",
            "recent accomplishments at work",
            "afternoon energy and focus",
            "interesting things you learned today",
        ],
        "evening": [
            "how the day went overall",
            "evening relaxation routines",
            "books, movies, or shows you're enjoying",
            "things you're grateful for today",
            "plans for tomorrow",
            "hobbies and personal projects",
        ],
        "night": [
            "reflections on the day",
            "thoughts before sleep",
            "calm and relaxing topics",
            "dreams and aspirations",
            "what you're looking forward to",
            "winding down and self-care",
        ],
    }

    # Follow-up topic templates
    FOLLOW_UP_TEMPLATES = [
        "Last time you mentioned {topic} — how's that going?",
        "I was thinking about our conversation on {topic} — any updates?",
        "You were telling me about {topic} before. I'm curious to hear more.",
        "Remember when we talked about {topic}? That was interesting.",
        "I've been wondering about {topic} since our last chat.",
    ]

    # Grammar challenge templates
    GRAMMAR_CHALLENGES = {
        "tense": [
            "past simple vs present perfect challenge",
            "telling a story using past tenses correctly",
            "describing your morning using past continuous",
            "talking about future plans with 'going to' vs 'will'",
        ],
        "preposition": [
            "describing your workspace (in, on, at practice)",
            "making plans — prepositions of time drill",
            "giving directions using place prepositions",
        ],
        "article": [
            "describing objects (a/an/the practice)",
            "talking about categories vs specific items",
        ],
        "conditional": [
            "hypothetical situations (if I were/would practice)",
            "talking about possibilities and what-ifs",
        ],
        "modal": [
            "giving advice using should/could/would",
            "making polite requests",
            "expressing obligations and possibilities",
        ],
        "pronoun": [
            "telling a story about two people — pronoun clarity",
            "possessives — talking about what belongs to whom",
        ],
    }

    def __init__(self, profile_manager=None):
        self._profile_manager = profile_manager
        self._recent_topics: deque = deque(maxlen=self.MAX_RECENT)
        self._recent_grammar: deque = deque(maxlen=5)
        self._session_count = 0

    def pick_topic(
        self,
        trigger_type: str = "random_interval",
        error_categories: list[str] | None = None,
    ) -> str:
        """
        Pick a topic for a spontaneous conversation opening.

        Args:
            trigger_type: 'random_interval', 'daily_checkin', 'post_silence', 'manual'
            error_categories: Recent frequent error categories to practice

        Returns:
            A topic string suitable for the LLM spontaneous prompt
        """
        # Decide topic source based on trigger type
        if trigger_type == "daily_checkin":
            source = self._get_checkin_topic()
        elif trigger_type == "post_silence":
            source = self._get_post_silence_topic()
        elif error_categories and random.random() < 0.3:
            # 30% chance to suggest grammar practice
            source = self._get_grammar_topic(error_categories)
        elif random.random() < 0.2 and len(self._recent_topics) > 2:
            # 20% chance for follow-up
            source = self._get_follow_up_topic()
        else:
            source = self._get_interest_or_general_topic()

        # Avoid repetition
        attempts = 0
        while source in self._recent_topics and attempts < 10:
            source = self._get_interest_or_general_topic()
            attempts += 1

        self._recent_topics.append(source)
        self._session_count += 1

        logger.debug(f"Selected topic: '{source}' (type={trigger_type})")

        return source

    def _get_checkin_topic(self) -> str:
        """Get a friendly check-in topic based on time of day."""
        time_of_day = self._get_time_of_day()
        options = self.TIME_TOPICS.get(time_of_day, self.TIME_TOPICS["afternoon"])

        if time_of_day == "morning":
            return f"morning check-in — {random.choice(options)}"
        elif time_of_day == "evening":
            return f"evening wind-down — {random.choice(options)}"
        else:
            return f"daily check-in — {random.choice(options)}"

    def _get_post_silence_topic(self) -> str:
        """Get a gentle re-engagement topic after silence."""
        options = [
            "a light, easy topic to ease back into conversation",
            "something fun and engaging — a game or challenge",
            "asking how they're feeling right now",
            "a quick, interesting fact or observation",
            "a vocabulary game or English trivia",
        ]
        return f"post-silence re-engagement — {random.choice(options)}"

    def _get_grammar_topic(self, error_categories: list[str]) -> str:
        """Get a grammar practice topic based on recent errors."""
        for category in error_categories:
            if category in self.GRAMMAR_CHALLENGES and category not in self._recent_grammar:
                self._recent_grammar.append(category)
                challenge = random.choice(self.GRAMMAR_CHALLENGES[category])
                return f"grammar practice: {category} — {challenge}"

        # Fallback: pick any available grammar topic
        all_grammar = []
        for challenges in self.GRAMMAR_CHALLENGES.values():
            all_grammar.extend(challenges)

        if all_grammar:
            return f"grammar practice: {random.choice(all_grammar)}"

        return self._get_interest_or_general_topic()

    def _get_follow_up_topic(self) -> str:
        """Get a follow-up topic from recent conversations."""
        if self._recent_topics:
            recent = random.choice(list(self._recent_topics)[-5:])
            # Extract a shorter topic name for the template
            short_topic = recent.split(" — ")[-1] if " — " in recent else recent
            template = random.choice(self.FOLLOW_UP_TEMPLATES)
            return template.format(topic=short_topic)

        return self._get_interest_or_general_topic()

    def _get_interest_or_general_topic(self) -> str:
        """Get a topic from user interests or general English conversation."""
        interests = self._get_user_interests()

        if interests and random.random() < 0.7:
            interest = random.choice(interests)
            angles = self._get_interest_angles(interest)
            angle = random.choice(angles)
            return f"interest-based: {interest} — {angle}"

        # Fallback to general English conversation topics
        general = [
            "travel experiences and dream destinations",
            "technology trends and innovations",
            "favorite books, movies, or music",
            "food and cooking adventures",
            "sports and fitness routines",
            "learning new skills and hobbies",
            "cultural differences and observations",
            "environmental awareness and sustainability",
            "personal growth and life lessons",
            "fun questions and hypothetical scenarios",
        ]

        return f"general conversation: {random.choice(general)}"

    def _get_interest_angles(self, interest: str) -> list[str]:
        """Generate conversation angles for a given interest."""
        interest_lower = interest.lower()

        base_angles = [
            f"their recent experience with {interest}",
            f"what they enjoy most about {interest}",
            f"how they got started with {interest}",
            f"their opinion on current trends in {interest}",
            f"something surprising or fun about {interest}",
            f"comparing {interest} in different cultures",
            f"future predictions about {interest}",
            f"recommendations and tips about {interest}",
        ]

        # Tech-specific angles
        if any(t in interest_lower for t in ["tech", "programming", "coding", "ai", "software"]):
            base_angles.extend([
                "new tools or languages they're exploring",
                "their take on AI and automation",
                "a technical challenge they recently solved",
                "conferences or communities they follow",
            ])

        return base_angles or ["their thoughts on this topic"]

    def _get_user_interests(self) -> list[str]:
        """Get user's declared interests from profile."""
        try:
            if self._profile_manager:
                return self._profile_manager.get_interests()
        except Exception:
            pass
        return []

    def _get_time_of_day(self) -> str:
        """Get current time of day as string."""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def record_session_topic(self, topic: str):
        """Record a topic that was actually discussed."""
        self._recent_topics.append(topic)

    def get_random_grammar_challenge(self) -> str:
        """Get a random grammar challenge for variety."""
        all_challenges = []
        for challenges in self.GRAMMAR_CHALLENGES.values():
            all_challenges.extend(challenges)
        return random.choice(all_challenges) if all_challenges else ""

    def clear_recent(self):
        """Clear recent topics list."""
        self._recent_topics.clear()
        self._recent_grammar.clear()
