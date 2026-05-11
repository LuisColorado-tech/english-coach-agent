"""
Processes LLM responses for the pipeline.
Handles extraction of corrections, vocabulary, and cleans text for TTS.
"""

import re
import json
from dataclasses import dataclass, field

from config.logging_config import setup_logging

logger = setup_logging()


@dataclass
class Correction:
    original: str
    corrected: str
    error_type: str  # grammar, vocabulary, pronunciation_hint, structure
    explanation: str
    error_category: str = ""


@dataclass
class ProcessedResponse:
    conversational_text: str  # Clean text ready for TTS
    corrections: list[Correction] = field(default_factory=list)
    new_vocabulary: list[dict] = field(default_factory=list)
    profile_updates: list[dict] = field(default_factory=list)
    raw_response: str = ""


class ResponseProcessor:
    """
    Processes raw LLM output into structured components:
    - Clean conversational text for TTS
    - Extracted corrections for logging and UI
    - New vocabulary entries
    - Profile update commands
    """

    # Pattern for inline corrections: [CORRECTION: original='...' corrected='...' type='...' explanation='...']
    CORRECTION_PATTERN = re.compile(
        r"\[CORRECTION:\s*"
        r"original='([^']*)'\s*"
        r"corrected='([^']*)'\s*"
        r"type='([^']*)'\s*"
        r"explanation='([^']*)'"
        r"(?:\s*category='([^']*)')?\s*\]",
        re.IGNORECASE,
    )

    # Pattern for profile updates: [PROFILE_UPDATE: field='...' value='...']
    PROFILE_UPDATE_PATTERN = re.compile(
        r"\[PROFILE_UPDATE:\s*field='([^']*)'\s*value='([^']*)'\s*\]",
        re.IGNORECASE,
    )

    # Pattern for new vocabulary: [NEW_WORD: word='...' definition='...']
    NEW_WORD_PATTERN = re.compile(
        r"\[NEW_WORD:\s*word='([^']*)'\s*definition='([^']*)'\s*\]",
        re.IGNORECASE,
    )

    # Error category mapping
    ERROR_CATEGORIES = {
        "tense": "tense",
        "preposition": "preposition",
        "article": "article",
        "word_order": "word_order",
        "subject_verb": "subject_verb_agreement",
        "plural": "plural",
        "pronoun": "pronoun",
        "vocabulary": "vocabulary",
        "pronunciation_hint": "pronunciation",
        "structure": "sentence_structure",
    }

    def process(self, raw_response: str) -> ProcessedResponse:
        """
        Process raw LLM response. Returns structured output with:
        - conversational_text: cleaned for TTS
        - corrections: list of Correction objects
        - new_vocabulary: list of word/definition dicts
        - profile_updates: list of field/value dicts
        """
        result = ProcessedResponse(raw_response=raw_response)

        conversational = raw_response

        # Extract corrections
        for match in self.CORRECTION_PATTERN.finditer(raw_response):
            original = match.group(1)
            corrected = match.group(2)
            error_type = match.group(3).lower()
            explanation = match.group(4)
            category = match.group(5) or error_type

            result.corrections.append(
                Correction(
                    original=original,
                    corrected=corrected,
                    error_type=error_type,
                    explanation=explanation,
                    error_category=self.ERROR_CATEGORIES.get(category, category),
                )
            )

            # Remove the CORRECTION tag from conversational text
            conversational = conversational.replace(match.group(0), "")

        # Extract profile updates
        for match in self.PROFILE_UPDATE_PATTERN.finditer(raw_response):
            result.profile_updates.append(
                {
                    "field": match.group(1),
                    "value": match.group(2),
                }
            )
            conversational = conversational.replace(match.group(0), "")

        # Extract new vocabulary
        for match in self.NEW_WORD_PATTERN.finditer(raw_response):
            result.new_vocabulary.append(
                {
                    "word": match.group(1),
                    "definition": match.group(2),
                }
            )
            conversational = conversational.replace(match.group(0), "")

        # Clean up conversational text
        conversational = self._clean_text(conversational)

        result.conversational_text = conversational

        logger.debug(
            f"Processed response: {len(result.corrections)} corrections, "
            f"{len(result.new_vocabulary)} new words, "
            f"{len(result.profile_updates)} profile updates"
        )

        return result

    def _clean_text(self, text: str) -> str:
        """Clean up text for TTS: remove extra whitespace, fix punctuation."""
        # Remove multiple spaces and newlines
        text = re.sub(r"\n+", " ", text)
        text = re.sub(r"\s{2,}", " ", text)

        # Remove leading/trailing whitespace
        text = text.strip()

        # Fix spacing around punctuation
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)

        # Ensure space after punctuation
        text = re.sub(r"([.,!?;:])([^\s\d])", r"\1 \2", text)

        return text

    def extract_corrections_summary(
        self, corrections: list[Correction]
    ) -> str:
        """Create a summary of corrections for the system prompt."""
        if not corrections:
            return ""

        by_category: dict[str, list[Correction]] = {}
        for c in corrections:
            by_category.setdefault(c.error_category, []).append(c)

        summary_parts = []
        for category, items in by_category.items():
            examples = [f"'{c.original}' → '{c.corrected}'" for c in items[-3:]]
            summary_parts.append(f"- {category}: {', '.join(examples)}")

        return "\n".join(summary_parts)

    def parse_correction_style(self, style: str) -> str:
        """Normalize correction style value."""
        valid_styles = {"immediate", "gentle", "end_of_sentence"}
        style = style.lower().strip()
        if style not in valid_styles:
            logger.warning(f"Unknown correction style '{style}', using 'gentle'")
            return "gentle"
        return style


def parse_topic_suggestions(error_categories: list[str]) -> list[dict]:
    """Generate topic study suggestions based on error categories."""
    topic_map = {
        "tense": {
            "topic": "Past simple vs Present perfect",
            "reason": "Common tense confusion detected",
        },
        "preposition": {
            "topic": "English prepositions (in/on/at)",
            "reason": "Preposition errors are frequent",
        },
        "article": {
            "topic": "Articles a/an/the usage",
            "reason": "Article usage needs practice",
        },
        "word_order": {
            "topic": "English sentence word order",
            "reason": "Word order patterns can be improved",
        },
        "subject_verb_agreement": {
            "topic": "Subject-Verb agreement rules",
            "reason": "Subject-verb matching practice needed",
        },
        "pronoun": {
            "topic": "Pronoun usage and reference",
            "reason": "Pronoun clarity could be improved",
        },
    }

    seen_topics = set()
    suggestions = []

    for category in error_categories:
        if category in topic_map and category not in seen_topics:
            seen_topics.add(category)
            suggestions.append(topic_map[category])

    return suggestions
