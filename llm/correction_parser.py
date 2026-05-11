"""
Robust correction parser for extracting structured corrections from LLM output.
Handles both inline [CORRECTION:...] tags and JSON-formatted corrections.
Validates, deduplicates, and categorizes corrections for storage and UI.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from config.logging_config import setup_logging

logger = setup_logging()


@dataclass
class ParsedCorrection:
    original: str
    corrected: str
    error_type: str  # grammar, vocabulary, pronunciation_hint, structure
    explanation: str
    error_category: str = ""  # tense, preposition, article, etc.
    confidence: float = 1.0
    raw_match: str = ""

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "corrected": self.corrected,
            "error_type": self.error_type,
            "explanation": self.explanation,
            "error_category": self.error_category,
        }


@dataclass
class ParsedNewWord:
    word: str
    definition: str
    example: str = ""

    def to_dict(self) -> dict:
        return {
            "word": self.word,
            "definition": self.definition,
            "example": self.example,
        }


@dataclass
class ParseResult:
    conversational_text: str
    corrections: list[ParsedCorrection] = field(default_factory=list)
    new_words: list[ParsedNewWord] = field(default_factory=list)
    profile_updates: list[dict] = field(default_factory=list)
    raw_text: str = ""
    parse_errors: list[str] = field(default_factory=list)


class CorrectionParser:
    """
    Robust parser for LLM output that extracts corrections, vocabulary,
    and profile updates from response text.
    """

    # Primary correction format: [CORRECTION: original='...' corrected='...' type='...' explanation='...']
    CORRECTION_REGEX = re.compile(
        r"\[CORRECTION:\s*"
        r"original='((?:[^'\\]|\\.)*)'\s*"  # Handle escaped quotes
        r"corrected='((?:[^'\\]|\\.)*)'\s*"
        r"type='((?:[^'\\]|\\.)*)'\s*"
        r"explanation='((?:[^'\\]|\\.)*)'"
        r"(?:\s*category='((?:[^'\\]|\\.)*)')?\s*\]",
        re.IGNORECASE | re.DOTALL,
    )

    # Alternative short format: [CORRECTION: original|corrected|type|explanation]
    CORRECTION_SHORT_REGEX = re.compile(
        r"\[CORRECTION:\s*"
        r"([^|]+)\s*\|\s*"
        r"([^|]+)\s*\|\s*"
        r"([^|]+)\s*\|\s*"
        r"([^\]]+)\s*\]",
        re.IGNORECASE,
    )

    # JSON correction format: {/* correction format */}
    JSON_CORRECTION_REGEX = re.compile(
        r'\{[^}]*"type"\s*:\s*"correction"[^}]*"original"[^}]*\}',
        re.IGNORECASE,
    )

    # New word format: [NEW_WORD: word='...' definition='...']
    NEW_WORD_REGEX = re.compile(
        r"\[NEW_WORD:\s*"
        r"word='((?:[^'\\]|\\.)*)'\s*"
        r"definition='((?:[^'\\]|\\.)*)'"
        r"(?:\s*example='((?:[^'\\]|\\.)*)')?\s*\]",
        re.IGNORECASE | re.DOTALL,
    )

    # Profile update format
    PROFILE_UPDATE_REGEX = re.compile(
        r"\[PROFILE_UPDATE:\s*"
        r"field='((?:[^'\\]|\\.)*)'\s*"
        r"value='((?:[^'\\]|\\.)*)'\s*\]",
        re.IGNORECASE | re.DOTALL,
    )

    # Error categorization patterns
    ERROR_CATEGORY_PATTERNS = {
        "tense": [r"\btense\b", r"\bpast\b", r"\bpresent\b", r"\bfuture\b",
                  r"\bperfect\b", r"\bcontinuous\b", r"\bconjugat"],
        "preposition": [r"\bpreposition\b", r"\bin\b.*\bon\b.*\bat\b",
                        r"\bto\b.*\bfor\b", r"\bfrom\b"],
        "article": [r"\barticle\b", r"\ba\b.*\ban\b.*\bthe\b"],
        "word_order": [r"\bword order\b", r"\border of words\b",
                       r"\bquestion formation\b"],
        "subject_verb_agreement": [r"\bsubject.verb\b", r"\bagreement\b",
                                    r"\bhe\b.*\bdon't\b"],
        "plural": [r"\bplural\b", r"\bsingular\b", r"\bcountable\b"],
        "pronoun": [r"\bpronoun\b", r"\bpossessive\b", r"\bhis\b.*\bher\b"],
        "modal": [r"\bmodal\b", r"\bshould\b", r"\bcould\b", r"\bwould\b",
                  r"\bcan\b.*\bcould\b"],
        "conditional": [r"\bconditional\b", r"\bif\b.*\bwould\b",
                        r"\bhypothetical\b"],
        "comparative": [r"\bcomparative\b", r"\bsuperlative\b",
                        r"\bmore\b.*\bthan\b", r"\b-er\b.*\b-est\b"],
    }

    VALID_ERROR_TYPES = {"grammar", "vocabulary", "pronunciation_hint", "structure"}

    def parse(self, raw_text: str) -> ParseResult:
        """
        Parse an LLM response and extract all structured data.

        Args:
            raw_text: Raw output from the LLM

        Returns:
            ParseResult with cleaned conversational text and extracted data
        """
        result = ParseResult(raw_text=raw_text)
        conversational = raw_text

        # Try primary format first
        full_corrections = self.CORRECTION_REGEX.finditer(raw_text)
        for match in full_corrections:
            try:
                correction = self._parse_primary_match(match)
                if correction:
                    result.corrections.append(correction)
                    conversational = conversational.replace(
                        match.group(0), "", 1
                    )
            except Exception as e:
                result.parse_errors.append(f"Correction parse error: {e}")

        # Try short format for remaining
        short_corrections = self.CORRECTION_SHORT_REGEX.finditer(conversational)
        for match in short_corrections:
            try:
                correction = self._parse_short_match(match)
                if correction:
                    result.corrections.append(correction)
                    conversational = conversational.replace(
                        match.group(0), "", 1
                    )
            except Exception as e:
                result.parse_errors.append(f"Short correction parse error: {e}")

        # Extract new vocabulary
        for match in self.NEW_WORD_REGEX.finditer(raw_text):
            try:
                word = match.group(1).strip()
                definition = match.group(2).strip()
                example = (match.group(3) or "").strip()

                if word and definition:
                    result.new_words.append(ParsedNewWord(
                        word=word,
                        definition=definition,
                        example=example,
                    ))
                    conversational = conversational.replace(
                        match.group(0), "", 1
                    )
            except Exception as e:
                result.parse_errors.append(f"New word parse error: {e}")

        # Extract profile updates
        for match in self.PROFILE_UPDATE_REGEX.finditer(raw_text):
            try:
                field = match.group(1).strip()
                value = match.group(2).strip()

                if field and value:
                    result.profile_updates.append({
                        "field": field,
                        "value": value,
                    })
                    conversational = conversational.replace(
                        match.group(0), "", 1
                    )
            except Exception as e:
                result.parse_errors.append(f"Profile update parse error: {e}")

        # Clean and normalize conversational text
        result.conversational_text = self._clean_text(conversational)

        # Post-process corrections (deduplicate, validate, categorize)
        result.corrections = self._post_process_corrections(result.corrections)

        if result.parse_errors:
            logger.warning(f"Parse errors: {result.parse_errors}")

        return result

    def _parse_primary_match(self, match: re.Match) -> ParsedCorrection | None:
        """Parse the primary [CORRECTION: key='value' ...] format."""
        original = self._unescape_quotes(match.group(1).strip())
        corrected = self._unescape_quotes(match.group(2).strip())
        error_type = self._unescape_quotes(match.group(3).strip().lower())
        explanation = self._unescape_quotes(match.group(4).strip())
        category = self._unescape_quotes(match.group(5).strip()) if match.group(5) else ""

        if not original or not corrected:
            return None

        # Validate error type
        if error_type not in self.VALID_ERROR_TYPES:
            error_type = self._infer_error_type(original, corrected, explanation)

        # Auto-categorize if no explicit category
        if not category:
            category = self._categorize_error(original, corrected, explanation)

        return ParsedCorrection(
            original=original,
            corrected=corrected,
            error_type=error_type,
            explanation=explanation,
            error_category=category,
            raw_match=match.group(0),
        )

    def _parse_short_match(self, match: re.Match) -> ParsedCorrection | None:
        """Parse the short [CORRECTION: a|b|c|d] format."""
        original = match.group(1).strip()
        corrected = match.group(2).strip()
        error_type = match.group(3).strip().lower()
        explanation = match.group(4).strip()

        if not original or not corrected:
            return None

        if error_type not in self.VALID_ERROR_TYPES:
            error_type = self._infer_error_type(original, corrected, explanation)

        category = self._categorize_error(original, corrected, explanation)

        return ParsedCorrection(
            original=original,
            corrected=corrected,
            error_type=error_type,
            explanation=explanation,
            error_category=category,
            raw_match=match.group(0),
        )

    def _infer_error_type(
        self, original: str, corrected: str, explanation: str
    ) -> str:
        """Infer the error type from the correction details."""
        combined = f"{original} {corrected} {explanation}".lower()

        if any(w in combined for w in ["tense", "past", "present", "conjugat",
                                        "future", "perfect", "verb form"]):
            return "grammar"
        if any(w in combined for w in ["word", "vocabulary", "meaning", "term"]):
            return "vocabulary"
        if any(w in combined for w in ["pronounce", "sound", "syllable", "stress"]):
            return "pronunciation_hint"
        if any(w in combined for w in ["structure", "order", "sentence",
                                        "phrase", "clause"]):
            return "structure"

        return "grammar"  # Default

    def _categorize_error(
        self, original: str, corrected: str, explanation: str
    ) -> str:
        """Auto-categorize the error into a specific category."""
        combined = f"{original} {corrected} {explanation}".lower()

        for category, patterns in self.ERROR_CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined):
                    return category

        return "grammar"

    def _post_process_corrections(
        self, corrections: list[ParsedCorrection]
    ) -> list[ParsedCorrection]:
        """Deduplicate and validate corrections."""
        seen = set()
        unique = []

        for c in corrections:
            key = (c.original.lower(), c.corrected.lower())
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique

    def _clean_text(self, text: str) -> str:
        """Clean text for TTS consumption."""
        # Remove extra whitespace and newlines
        text = re.sub(r"\n+", " ", text)
        text = re.sub(r" {2,}", " ", text)

        # Remove markdown formatting
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)

        # Fix punctuation spacing
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        text = re.sub(r"([.,!?;:])([^\s\d])", r"\1 \2", text)

        # Remove any remaining unclosed tags
        text = re.sub(r"\[CORRECTION:.*?$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[NEW_WORD:.*?$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[PROFILE_UPDATE:.*?$", "", text, flags=re.IGNORECASE)

        # Fix spacing between sentences
        text = re.sub(r"\.([A-Z])", r". \1", text)

        text = text.strip()

        # Ensure it ends with proper punctuation
        if text and text[-1] not in ".!?":
            text += "."

        return text

    def _unescape_quotes(self, text: str) -> str:
        """Unescape quotes within correction values."""
        return text.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")

    def extract_corrections_only(self, raw_text: str) -> list[dict]:
        """Convenience method: extract only corrections as dicts."""
        result = self.parse(raw_text)
        return [c.to_dict() for c in result.corrections]

    def extract_new_words_only(self, raw_text: str) -> list[dict]:
        """Convenience method: extract only new words as dicts."""
        result = self.parse(raw_text)
        return [w.to_dict() for w in result.new_words]

    def get_conversational_text(self, raw_text: str) -> str:
        """Convenience method: get clean text for TTS."""
        result = self.parse(raw_text)
        return result.conversational_text


class CorrectionValidator:
    """
    Validates correction quality and prevents false positives.
    Ensures the agent only corrects genuine errors.
    """

    MIN_ORIGINAL_LENGTH = 2
    MAX_ORIGINAL_LENGTH = 200
    MIN_EXPLANATION_LENGTH = 5
    MAX_EXPLANATION_LENGTH = 500

    # Patterns that indicate the correction might be fabricated or low-quality
    SUSPICIOUS_PATTERNS = [
        r"^\s*$",                    # Empty
        r"^[.,!?;:]+$",              # Only punctuation
        r"^[a-zA-Z]{1}$",            # Single letter
        r"^(ok|okay|yes|no|hi|bye)$",# Common one-word responses
    ]

    @classmethod
    def is_valid(cls, correction: ParsedCorrection) -> bool:
        """Check if a correction is valid and likely genuine."""
        if not correction.original or not correction.corrected:
            return False

        original = correction.original.strip()

        # Length checks
        if len(original) < cls.MIN_ORIGINAL_LENGTH:
            return False
        if len(original) > cls.MAX_ORIGINAL_LENGTH:
            return False

        # Explanation must be meaningful
        if len(correction.explanation) < cls.MIN_EXPLANATION_LENGTH:
            return False
        if len(correction.explanation) > cls.MAX_EXPLANATION_LENGTH:
            return False

        # Suspect patterns
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.match(pattern, original, re.IGNORECASE):
                return False

        # Original and corrected should be different
        if original.lower() == correction.corrected.lower():
            return False

        return True

    @classmethod
    def filter_valid(cls, corrections: list[ParsedCorrection]) -> list[ParsedCorrection]:
        """Return only valid corrections."""
        return [c for c in corrections if cls.is_valid(c)]
