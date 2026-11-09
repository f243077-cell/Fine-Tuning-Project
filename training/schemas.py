"""Pydantic schema and enums for JSONL data rows (Architecture.md section 9)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Source(StrEnum):
    """Where the text came from."""

    USER_INPUT = "user_input"
    RETRIEVED_CHUNK = "retrieved_chunk"
    TOOL_OUTPUT = "tool_output"


class Label(StrEnum):
    """Top-level class of a row."""

    SAFE = "SAFE"
    INJECTION = "INJECTION"


class AttackType(StrEnum):
    """Kind of injection; only set when the label is INJECTION."""

    OVERRIDE = "override"
    PERSONA = "persona"
    PROMPT_LEAK = "prompt_leak"
    EXFILTRATION = "exfiltration"
    TOOL_ABUSE = "tool_abuse"


class Surface(StrEnum):
    """Surface form of the text."""

    EN = "en"
    RU_MIX = "ru_mix"
    RU_PURE = "ru_pure"


class Origin(StrEnum):
    """How the row was made."""

    SEED = "seed"
    SYNTHETIC = "synthetic"
    TEST = "test"


class DataRow(BaseModel):
    """One labeled JSONL row."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: Source
    label: Label
    attack_type: AttackType | None = None
    surface: Surface
    origin: Origin
    intent_id: str | None = None
    hard_negative: bool = False

    @model_validator(mode="after")
    def _check_consistency(self) -> "DataRow":
        """Enforce label/attack_type pairing and intent_id on test rows."""
        if not self.text.strip():
            raise ValueError("text must not be blank")
        if self.label == Label.INJECTION and self.attack_type is None:
            raise ValueError("attack_type is required when label is INJECTION")
        if self.label == Label.SAFE and self.attack_type is not None:
            raise ValueError("attack_type must be empty when label is SAFE")
        if self.label == Label.INJECTION and self.hard_negative:
            raise ValueError("hard_negative is only allowed on SAFE rows")
        if self.origin == Origin.TEST and not self.intent_id:
            raise ValueError("intent_id is required for test rows")
        return self

    @property
    def target(self) -> str:
        """Model output string: SAFE or INJECTION|<attack_type>."""
        return Label.SAFE.value if self.label == Label.SAFE else f"INJECTION|{self.attack_type}"
