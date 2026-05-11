"""
Dynamic context builder for the English Coach Agent.
Constructs the full system prompt before each session by injecting:
- User profile data (name, level, profession, interests)
- Recent error patterns from past sessions
- Correction style preferences
- Spontaneous trigger additions when applicable
"""

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config.settings import (
    DB_PATH,
    MAX_CONTEXT_TOKENS,
    RECENT_ERRORS_SESSIONS,
    MAX_ERRORS_INJECTED,
)
from config.logging_config import setup_logging
from memory.profile_manager import ProfileManager

logger = setup_logging()


@dataclass
class ContextSection:
    title: str
    content: str
    priority: int = 0  # Lower = more important, included first


@dataclass
class SystemPromptContext:
    user_name: str
    native_language: str
    location: str
    level: str
    learning_goal: str
    interests: list[str]
    avoid_topics: list[str]
    role: str
    company: str
    skills: list[str]
    personality_notes: str
    correction_style: str
    recent_errors_summary: str
    is_spontaneous: bool = False
    spontaneous_context: str = ""
    profile: dict = field(default_factory=dict)


class ContextBuilder:
    """
    Builds the complete system prompt for each session.
    Reads user profile and recent error history to personalize the agent's behavior.
    """

    CORRECTION_STYLES = {
        "immediate": (
            "Correct errors the MOMENT you hear them — inline, mid-response. "
            "Interrupt yourself to correct before continuing. Format: "
            "'Actually, we say [CORRECTION: original='...' corrected='...' type='grammar' "
            "explanation='brief reason']. Anyway, as I was saying...'"
        ),
        "gentle": (
            "Acknowledge what the user said first, then gently correct at the end "
            "of your turn. Format: 'Great point! Just a quick note — "
            "[CORRECTION: original='...' corrected='...' type='grammar' "
            "explanation='brief reason']. [continues naturally]'"
        ),
        "end_of_sentence": (
            "Wait until the user finishes their full thought, then respond normally. "
            "Add corrections at the very end of your response. Format: "
            "'[normal response]. Oh, and one thing: you said "
            "[CORRECTION: original='...' corrected='...' type='grammar' "
            "explanation='brief reason']'"
        ),
    }

    def __init__(self, db_path: str | None = None):
        self._profile_manager = ProfileManager()
        self._db_path = db_path or str(DB_PATH)

    def build(
        self,
        is_spontaneous: bool = False,
        spontaneous_topic: str = "",
        extra_instructions: str = "",
    ) -> str:
        """
        Build the full system prompt for the current session.

        Args:
            is_spontaneous: Whether the agent initiated this conversation
            spontaneous_topic: Topic to use when opening spontaneously
            extra_instructions: Additional session-specific instructions

        Returns:
            Complete system prompt string ready for DeepSeek
        """
        profile = self._load_profile()
        ctx = self._extract_context(profile, is_spontaneous, spontaneous_topic)
        prompt = self._compose_prompt(ctx, extra_instructions)
        return prompt

    def _load_profile(self) -> dict:
        """Load user profile via ProfileManager with validation."""
        return self._profile_manager.to_dict()

    def _extract_context(
        self,
        profile: dict,
        is_spontaneous: bool,
        spontaneous_topic: str,
    ) -> SystemPromptContext:
        """Extract structured context from profile."""
        user = profile.get("user", {})
        eng = profile.get("english_profile", {})
        pro = profile.get("professional_profile", {})
        per = profile.get("personal_profile", {})
        cfg = profile.get("agent_config", {})

        # Get recent error summary
        recent_errors = self._get_recent_errors_summary()

        return SystemPromptContext(
            user_name=user.get("name", "there"),
            native_language=user.get("native_language", "Spanish"),
            location=user.get("location", ""),
            level=eng.get("current_level", "intermediate"),
            learning_goal=eng.get("learning_goal", "Improve conversational fluency"),
            interests=eng.get("topics_of_interest", []),
            avoid_topics=eng.get("topics_to_avoid", []),
            role=pro.get("role", "professional"),
            company=pro.get("company", ""),
            skills=pro.get("skills", []),
            personality_notes=per.get("personality_notes", ""),
            correction_style=cfg.get("correction_style", "gentle"),
            recent_errors_summary=recent_errors,
            is_spontaneous=is_spontaneous,
            spontaneous_context=spontaneous_topic,
            profile=profile,
        )

    def _get_recent_errors_summary(self) -> str:
        """Query recent errors. Uses JSON fallback since DB access is async."""
        # Fallback: read from session_last.json if available
        try:
            from config.settings import DATA_DIR

            session_file = DATA_DIR / "session_last.json"
            if session_file.exists():
                data = json.loads(session_file.read_text())
                corrections = data.get("total_corrections", 0)
                if corrections > 0:
                    return (f"The user had {corrections} corrections in their "
                            f"last session. Watch for patterns and help them improve.")
        except Exception:
            pass

        return "No recent error data available. Observe and correct as needed."

    def _compose_prompt(
        self,
        ctx: SystemPromptContext,
        extra_instructions: str,
    ) -> str:
        """
        Compose the final system prompt from context sections.
        """
        # Get correction style instructions
        style_instructions = self.CORRECTION_STYLES.get(
            ctx.correction_style,
            self.CORRECTION_STYLES["gentle"],
        )

        # Format interests and avoid topics
        interests_str = ", ".join(ctx.interests) if ctx.interests else "various topics"
        avoid_str = ", ".join(ctx.avoid_topics) if ctx.avoid_topics else "none specified"

        # Professional context
        if ctx.company:
            professional_line = f"Professional context: {ctx.role} at {ctx.company}"
        else:
            professional_line = f"Professional context: {ctx.role}"

        if ctx.skills:
            skills_str = ", ".join(ctx.skills[:5])  # Top 5 skills
            professional_line += f", skilled in {skills_str}"

        # Location
        location_line = f"from {ctx.location}" if ctx.location else ""

        # Personality notes
        personality_line = ""
        if ctx.personality_notes:
            personality_line = (
                f"Personality notes about {ctx.user_name}: {ctx.personality_notes}\n"
                "Reference these traits naturally in conversation — "
                "they help you connect better."
            )

        # Build prompt sections
        prompt = f"""You are Aria, an English conversation coach and companion.

=== WHO YOU ARE TALKING TO ===
- Name: {ctx.user_name}
- Native language: {ctx.native_language}
- English level: {ctx.level}
- Location: {location_line if location_line else "Unknown"}
- Learning goal: {ctx.learning_goal}

=== PROFESSIONAL CONTEXT ===
{professional_line}

=== INTERESTS & TOPICS ===
Topics they enjoy: {interests_str}
Topics to avoid: {avoid_str}

=== CORRECTION BEHAVIOR ===
{style_instructions}

Correction format rules:
- Use EXACTLY this format for every correction:
  [CORRECTION: original='USER_ORIGINAL_TEXT' corrected='CORRECTED_TEXT' type='TYPE' explanation='BRIEF_REASON']
- TYPE must be one of: grammar, vocabulary, pronunciation_hint, structure
- For vocabulary corrections, also use:
  [NEW_WORD: word='WORD' definition='BRIEF_DEFINITION']
- Maximum 1-2 corrections per response — choose the most important ones
- After correcting, continue the conversation naturally — don't dwell on errors
- NEVER fabricate corrections to seem helpful. Only correct genuine errors.

=== RECENT ERROR PATTERNS ===
{ctx.recent_errors_summary}

=== PERSONALITY ===
{personality_line if personality_line else "Be warm, encouraging, and treat the conversation like a natural chat with a friend."}

=== RESPONSE RULES ===
1. Always respond in English. If the user speaks Spanish, gently remind them in English.
2. Keep responses conversational (2-4 sentences) — avoid long lectures.
3. Reference things the user has shared before — show you remember.
4. Introduce new vocabulary organically when it fits naturally.
5. Suggest grammar topics to practice when you notice repeated errors.
6. Use a natural, warm tone — like a friend, not a textbook.
7. If the user seems tired or unfocused, offer a lighter topic or game.
8. If you don't understand, ask for clarification naturally."""

        # Add spontaneous context if applicable
        if ctx.is_spontaneous:
            prompt += f"""

=== SPONTANEOUS CONVERSATION ===
You are initiating this conversation spontaneously. {ctx.spontaneous_context}
Pick an interesting topic from their interests or something you remember from past conversations.
Start with a natural, engaging opening — like a friend who just thought of something interesting.
Keep it brief and inviting. Don't mention that you're starting spontaneously."""

        # Add extra instructions
        if extra_instructions:
            prompt += f"\n\n=== SESSION INSTRUCTIONS ===\n{extra_instructions}"

        # Validate token count (rough estimation: 4 chars ≈ 1 token)
        estimated_tokens = len(prompt) // 4
        if estimated_tokens > MAX_CONTEXT_TOKENS:
            logger.warning(
                f"System prompt may exceed token limit: "
                f"~{estimated_tokens} tokens (max {MAX_CONTEXT_TOKENS})"
            )

        logger.debug(f"Built system prompt: ~{estimated_tokens} estimated tokens")

        return prompt

    def build_spontaneous_prompt(self, topic: str = "") -> str:
        """
        Build a prompt specifically for spontaneous conversation initiation.
        Returns a concise prompt for the opening message.
        """
        profile = self._load_profile()
        ctx = self._extract_context(profile, True, topic)

        user_name = ctx.user_name
        interests = ctx.interests
        time_of_day = self._get_time_of_day()

        interests_hint = ""
        if interests:
            picked = interests[0] if interests else "technology"
            interests_hint = f"They're interested in {picked}. "

        spontaneous_context = (
            f"It's currently {time_of_day}. {interests_hint}"
            f"Pick a topic that fits this time of day and their interests. "
            f"Start with a brief, friendly greeting and an engaging observation or question."
        )

        # Build a shorter prompt for spontaneous triggers
        prompt = f"""You are Aria, {user_name}'s English conversation coach. 
You are starting a spontaneous conversation. It's {time_of_day}.

Be natural — like a friend checking in. Start with a brief, friendly greeting and 
an interesting observation or question related to their interests ({interests_str if interests else 'technology'}).

Keep it very short (1-2 sentences). Don't mention you're starting spontaneously.

IMPORTANT: This is just the opening — wait for them to respond before continuing."""

        return prompt

    def build_summary_prompt(self, conversation_text: str) -> str:
        """
        Build a prompt for generating a session summary.
        Used at the end of a session.
        """
        return f"""Based on this conversation session, generate a brief JSON summary 
with these fields. Return ONLY valid JSON, no other text.

Fields:
- topics_covered: array of strings (main topics discussed)
- corrections_count: integer (number of corrections made)
- new_vocabulary: array of strings (new words/phrases introduced)
- recommended_study_topic: string with reason (based on error patterns observed)
- session_highlights: string (1-2 sentence summary of the session)

Conversation:
{conversation_text[:3000]}
"""

    def _get_time_of_day(self) -> str:
        """Get a human-readable time of day."""
        try:
            hour = datetime.now().hour
            if 5 <= hour < 12:
                return "morning"
            elif 12 <= hour < 17:
                return "afternoon"
            elif 17 <= hour < 21:
                return "evening"
            else:
                return "night"
        except Exception:
            return "day"

    def invalidate_cache(self):
        """Clear the profile cache to force re-read on next build."""
        self._profile_manager = ProfileManager()

    def get_profile_summary(self) -> str:
        """Return a human-readable summary of the user profile."""
        return self._profile_manager.get_summary()
