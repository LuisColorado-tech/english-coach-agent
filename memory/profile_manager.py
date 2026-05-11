"""
Profile manager — reads, validates, and updates the user profile JSON.
Uses Pydantic for schema validation and supports auto-updates from LLM
PROFILE_UPDATE commands when the user shares new information.
"""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ValidationError

from config.settings import PROFILE_PATH, DATA_DIR, TTS_DEFAULT_VOICE
from config.logging_config import setup_logging

logger = setup_logging()


# === Enums ===

class EnglishLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    UPPER_INTERMEDIATE = "upper_intermediate"
    ADVANCED = "advanced"


class Accent(str, Enum):
    AMERICAN = "american"
    BRITISH = "british"
    AUSTRALIAN = "australian"


class CorrectionStyle(str, Enum):
    IMMEDIATE = "immediate"
    GENTLE = "gentle"
    END_OF_SENTENCE = "end_of_sentence"


# === Pydantic Models ===

class UserProfile(BaseModel):
    name: str = Field(default="there", min_length=1, max_length=100)
    native_language: str = Field(default="Spanish", max_length=50)
    location: str = Field(default="", max_length=200)
    timezone: str = Field(default="America/Bogota", max_length=50)


class EnglishProfile(BaseModel):
    current_level: EnglishLevel = Field(default=EnglishLevel.INTERMEDIATE)
    learning_goal: str = Field(
        default="Improve conversational fluency", max_length=500
    )
    preferred_accent: Accent = Field(default=Accent.AMERICAN)
    topics_of_interest: list[str] = Field(default_factory=lambda: ["technology"])
    topics_to_avoid: list[str] = Field(default_factory=list)

    @field_validator("topics_of_interest", "topics_to_avoid", mode="before")
    @classmethod
    def ensure_list_strings(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(item) for item in v]


class ProfessionalProfile(BaseModel):
    role: str = Field(default="professional", max_length=200)
    company: str = Field(default="", max_length=200)
    industry: str = Field(default="", max_length=200)
    skills: list[str] = Field(default_factory=list)
    current_projects: list[str] = Field(default_factory=list)

    @field_validator("skills", "current_projects", mode="before")
    @classmethod
    def ensure_list_strings(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(item) for item in v]


class PersonalProfile(BaseModel):
    hobbies: list[str] = Field(default_factory=list)
    personality_notes: str = Field(default="", max_length=1000)
    communication_style: str = Field(default="", max_length=500)

    @field_validator("hobbies", mode="before")
    @classmethod
    def ensure_list_strings(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(item) for item in v]


class AgentConfig(BaseModel):
    correction_style: CorrectionStyle = Field(default=CorrectionStyle.GENTLE)
    spontaneous_triggers_enabled: bool = Field(default=True)
    spontaneous_interval_minutes: int = Field(default=60, ge=15, le=480)
    daily_checkin_time: str = Field(default="09:00", max_length=5)
    tts_voice: str = Field(default=TTS_DEFAULT_VOICE, max_length=100)
    ui_always_on_top: bool = Field(default=True)


class ProfileMeta(BaseModel):
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    profile_version: str = Field(default="1.0.0")


class FullProfile(BaseModel):
    user: UserProfile = Field(default_factory=UserProfile)
    english_profile: EnglishProfile = Field(default_factory=EnglishProfile)
    professional_profile: ProfessionalProfile = Field(default_factory=ProfessionalProfile)
    personal_profile: PersonalProfile = Field(default_factory=PersonalProfile)
    agent_config: AgentConfig = Field(default_factory=AgentConfig)
    meta: ProfileMeta = Field(default_factory=ProfileMeta)


# === Profile Manager ===

class ProfileManager:
    """
    Manages the user's profile JSON file.
    Provides validated read/write access and handles profile updates
    triggered by the LLM when the user shares new information.
    """

    # Mapping of LLM PROFILE_UPDATE field names to nested Pydantic fields
    FIELD_MAPPING = {
        # user fields
        "name": ("user", "name"),
        "native_language": ("user", "native_language"),
        "location": ("user", "location"),
        "timezone": ("user", "timezone"),
        # english_profile fields
        "level": ("english_profile", "current_level"),
        "current_level": ("english_profile", "current_level"),
        "learning_goal": ("english_profile", "learning_goal"),
        "accent": ("english_profile", "preferred_accent"),
        "preferred_accent": ("english_profile", "preferred_accent"),
        "interests": ("english_profile", "topics_of_interest"),
        "topics_of_interest": ("english_profile", "topics_of_interest"),
        "topics_to_avoid": ("english_profile", "topics_to_avoid"),
        # professional_profile fields
        "role": ("professional_profile", "role"),
        "company": ("professional_profile", "company"),
        "industry": ("professional_profile", "industry"),
        "skills": ("professional_profile", "skills"),
        "current_projects": ("professional_profile", "current_projects"),
        "projects": ("professional_profile", "current_projects"),
        # personal_profile fields
        "hobbies": ("personal_profile", "hobbies"),
        "personality_notes": ("personal_profile", "personality_notes"),
        "personality": ("personal_profile", "personality_notes"),
        "communication_style": ("personal_profile", "communication_style"),
        # agent_config fields
        "correction_style": ("agent_config", "correction_style"),
        "tts_voice": ("agent_config", "tts_voice"),
        "voice": ("agent_config", "tts_voice"),
        "spontaneous_interval": ("agent_config", "spontaneous_interval_minutes"),
        "daily_checkin_time": ("agent_config", "daily_checkin_time"),
    }

    def __init__(self, profile_path: str | Path | None = None):
        self._profile_path = Path(profile_path or PROFILE_PATH)
        self._model: FullProfile | None = None

    def exists(self) -> bool:
        """Check if a profile file already exists."""
        return self._profile_path.exists()

    @property
    def profile(self) -> FullProfile:
        """Get current profile. Creates default if none loaded."""
        if self._model is None:
            self._model = self._load_or_create()
        return self._model

    def _load_or_create(self) -> FullProfile:
        """Load existing profile or create a default one."""
        if self._profile_path.exists():
            try:
                return self._load_from_disk()
            except Exception as e:
                logger.warning(
                    f"Profile file is corrupt: {e}. Starting with empty profile. "
                    f"Run setup wizard to reconfigure."
                )

        # Create default profile
        model = FullProfile()
        self._save_to_disk(model)
        logger.info("Created default profile")
        return model

    def _load_from_disk(self) -> FullProfile:
        """Load and validate profile from disk."""
        raw = self._profile_path.read_text(encoding="utf-8")
        data = json.loads(raw)

        try:
            model = FullProfile(**data)
            logger.debug(f"Profile loaded for user: {model.user.name}")
            return model
        except ValidationError as e:
            logger.warning(f"Profile validation failed, attempting repair: {e}")
            return self._repair_profile(data)

    def _repair_profile(self, data: dict) -> FullProfile:
        """
        Attempt to repair a profile with validation errors.
        Applies defaults for any invalid/missing fields.
        """
        default = FullProfile()
        default_dict = default.model_dump(mode="json")

        # Deep merge: keep valid user data, fill missing with defaults
        for section_name, section_default in default_dict.items():
            if section_name in data:
                if isinstance(section_default, dict) and isinstance(data[section_name], dict):
                    merged = {**section_default, **data[section_name]}
                    data[section_name] = merged
            else:
                data[section_name] = section_default

        try:
            model = FullProfile(**data)
            logger.info("Profile repaired successfully")
            self._save_to_disk(model)
            return model
        except ValidationError as e:
            logger.error(f"Profile repair failed: {e}. Using defaults.")
            return default

    def _save_to_disk(self, model: FullProfile):
        """Save profile model to disk as JSON."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        model.meta.last_updated = datetime.now(timezone.utc).isoformat()

        data = model.model_dump(mode="json")

        self._profile_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.debug(f"Profile saved: {self._profile_path}")

    # === Read operations ===

    def get_user_name(self) -> str:
        return self.profile.user.name

    def get_level(self) -> str:
        return self.profile.english_profile.current_level.value

    def get_native_language(self) -> str:
        return self.profile.user.native_language

    def get_location(self) -> str:
        return self.profile.user.location

    def get_role(self) -> str:
        return self.profile.professional_profile.role

    def get_company(self) -> str:
        return self.profile.professional_profile.company

    def get_interests(self) -> list[str]:
        return self.profile.english_profile.topics_of_interest

    def get_avoid_topics(self) -> list[str]:
        return self.profile.english_profile.topics_to_avoid

    def get_correction_style(self) -> str:
        return self.profile.agent_config.correction_style.value

    def get_tts_voice(self) -> str:
        return self.profile.agent_config.tts_voice

    def get_spontaneous_enabled(self) -> bool:
        return self.profile.agent_config.spontaneous_triggers_enabled

    def get_spontaneous_interval(self) -> int:
        return self.profile.agent_config.spontaneous_interval_minutes

    def to_dict(self) -> dict:
        """Return full profile as a dictionary."""
        return self.profile.model_dump(mode="json")

    def to_json(self) -> str:
        """Return full profile as JSON string."""
        return json.dumps(self.profile.model_dump(mode="json"), indent=2, ensure_ascii=False)

    # === Update operations ===

    def apply_update(self, field: str, value: str) -> bool:
        """
        Apply a single profile update from the LLM.
        Uses PROFILE_UPDATE format: field='role' value='Developer'

        Returns True if the update was applied, False if rejected.
        """
        if field not in self.FIELD_MAPPING:
            logger.debug(f"Unknown profile field: '{field}' — ignored")
            return False

        section, attr = self.FIELD_MAPPING[field]

        try:
            model_dict = self.profile.model_dump(mode="json")
            section_data = model_dict[section]

            # Handle list types
            if isinstance(section_data[attr], list):
                # For lists, we append unique values
                current = section_data[attr]
                if value not in current:
                    current.append(value)
                    section_data[attr] = current
                else:
                    return False  # Already present, no change
            else:
                # For scalar values, we overwrite
                section_data[attr] = value

            model_dict[section] = section_data

            # Re-validate
            self._model = FullProfile(**model_dict)
            self._save_to_disk(self._model)

            logger.info(f"Profile updated: {field} = '{value}'")
            return True

        except ValidationError as e:
            logger.warning(f"Failed to apply profile update '{field}': {e}")
            return False

    def apply_updates(self, updates: list[dict]) -> int:
        """
        Apply multiple profile updates.

        Args:
            updates: List of {"field": "...", "value": "..."} dicts

        Returns:
            Number of successful updates
        """
        applied = 0
        for update in updates:
            if self.apply_update(update.get("field", ""), update.get("value", "")):
                applied += 1
        return applied

    def update_field(self, section: str, field: str, value):
        """Directly update a specific profile field."""
        try:
            model_dict = self.profile.model_dump(mode="json")
            if section in model_dict:
                model_dict[section][field] = value
                self._model = FullProfile(**model_dict)
                self._save_to_disk(self._model)
                logger.info(f"Profile updated: {section}.{field}")
                return True
        except Exception as e:
            logger.warning(f"Field update failed: {e}")
        return False

    def update_entire_profile(self, data: dict) -> bool:
        """
        Replace the entire profile with new data.
        Validates before saving. Used by setup wizard.
        """
        try:
            self._model = FullProfile(**data)
            if "meta" not in data or "created_at" not in data.get("meta", {}):
                self._model.meta.created_at = datetime.now(timezone.utc).isoformat()
            self._save_to_disk(self._model)
            logger.info("Profile replaced with new data")
            return True
        except ValidationError as e:
            logger.error(f"Profile validation failed: {e}")
            return False

    def is_first_run(self) -> bool:
        """Check if this is the first run (no profile or default only)."""
        if not self._profile_path.exists():
            return True

        # Check if the profile has user-specific data or is just defaults
        profile = self.profile
        if profile.user.name in ("there", "", "User"):
            return True

        return False

    def reset(self, keep_backup: bool = True):
        """
        Reset profile to defaults.

        Args:
            keep_backup: If True, rename old file instead of deleting
        """
        if keep_backup and self._profile_path.exists():
            backup_path = self._profile_path.with_suffix(
                f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            self._profile_path.rename(backup_path)
            logger.info(f"Profile backed up to: {backup_path}")

        self._model = FullProfile()
        self._save_to_disk(self._model)
        logger.info("Profile reset to defaults")

    def get_summary(self) -> str:
        """Get a human-readable summary of the profile."""
        p = self.profile
        return (
            f"Name: {p.user.name}\n"
            f"Level: {p.english_profile.current_level.value}\n"
            f"Native: {p.user.native_language}\n"
            f"Location: {p.user.location or 'Not set'}\n"
            f"Role: {p.professional_profile.role}"
            + (f" at {p.professional_profile.company}" if p.professional_profile.company else "")
            + f"\nInterests: {', '.join(p.english_profile.topics_of_interest) if p.english_profile.topics_of_interest else 'None'}\n"
            f"Correction style: {p.agent_config.correction_style.value}\n"
            f"Spontaneous mode: {'On' if p.agent_config.spontaneous_triggers_enabled else 'Off'}\n"
            f"Profile version: {p.meta.profile_version}"
        )
