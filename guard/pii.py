"""PII masking for quarantined text (Architecture.md section 14).

Presidio analyzer with spaCy `en_core_web_sm` (pinned in requirements.txt as a wheel URL, so
`pip install -r requirements.txt` installs it; or run `python -m spacy download en_core_web_sm`),
plus two custom recognizers: Pakistani CNIC (#####-#######-#) and Pakistani phone numbers.
"""

import logging
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

logger = logging.getLogger("guard.pii")

SPACY_MODEL = "en_core_web_sm"

# Entities replaced by <ENTITY> in quarantined text. Dates and organisations are kept for readability.
MASKED_ENTITIES = [
    "PK_CNIC", "PK_PHONE", "PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD", "IBAN_CODE",
    "IP_ADDRESS", "PERSON", "LOCATION", "US_SSN", "URL",
]
SCORE_THRESHOLD = 0.4

CNIC_PATTERNS = [
    Pattern("cnic_dashed", r"(?<!\d)\d{5}-\d{7}-\d(?!\d)", 0.95),
    Pattern("cnic_plain", r"(?<!\d)\d{13}(?!\d)", 0.4),
]
PHONE_PATTERNS = [
    # Mobile: 03XX-XXXXXXX, 03XXXXXXXXX, +92 3XX XXXXXXX, 0092-3XX-XXXXXXX
    Pattern("pk_mobile", r"(?<![\d+])(?:\+92|0092|92|0)[ -]?3\d{2}[ -]?\d{7}(?!\d)", 0.9),
    # Landline: 042-35761234, +92 42 35761234, 021 1234567
    Pattern("pk_landline", r"(?<![\d+])(?:\+92[ -]?|0092[ -]?|0)(?:[2-9]\d{1,2})[ -]\d{6,8}(?!\d)", 0.6),
]
CNIC_CONTEXT = ["cnic", "shanakhti", "id card", "nic", "shanakht"]
PHONE_CONTEXT = ["phone", "mobile", "number", "call", "whatsapp", "fone", "nambar", "raabta", "rabta"]


def custom_recognizers() -> list[PatternRecognizer]:
    """CNIC and Pakistani phone recognizers."""
    return [
        PatternRecognizer(supported_entity="PK_CNIC", name="pk_cnic", patterns=CNIC_PATTERNS, context=CNIC_CONTEXT),
        PatternRecognizer(supported_entity="PK_PHONE", name="pk_phone", patterns=PHONE_PATTERNS, context=PHONE_CONTEXT),
    ]


class PiiMasker:
    """Find PII with Presidio and replace each span with <ENTITY_TYPE>."""

    def __init__(self) -> None:
        """Load the spaCy model and register the custom recognizers."""
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": SPACY_MODEL}]})
        self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        for rec in custom_recognizers():
            self.analyzer.registry.add_recognizer(rec)
        self.anonymizer = AnonymizerEngine()

    def find(self, text: str) -> list[RecognizerResult]:
        """PII spans above the score threshold."""
        return self.analyzer.analyze(text=text, language="en", entities=MASKED_ENTITIES,
                                     score_threshold=SCORE_THRESHOLD)

    def mask(self, text: str) -> str:
        """Text with every PII span replaced by <ENTITY_TYPE>."""
        results = self.find(text)
        if not results:
            return text
        operators = {"DEFAULT": OperatorConfig("replace", {"new_value": "<PII>"})}
        operators.update({e: OperatorConfig("replace", {"new_value": f"<{e}>"}) for e in MASKED_ENTITIES})
        return self.anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text


@lru_cache(maxsize=1)
def get_masker() -> PiiMasker:
    """Process-wide masker (the spaCy model is loaded once)."""
    logger.info("loading PII masker (spaCy %s)", SPACY_MODEL)
    return PiiMasker()
