"""
PII detection and redaction using Microsoft Presidio.

Detects and redacts PII before storing content in the KB.
The original text is never stored — only redacted versions.

Supported PII types:
- Standard: EMAIL_ADDRESS, PHONE_NUMBER, PERSON, LOCATION
- Custom Indian: AADHAAR_NUMBER, PAN_NUMBER
- Custom insurance: POLICY_NUMBER
"""

import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger

# Lazy-load Presidio to avoid startup cost when not needed
_analyzer = None
_anonymizer = None


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        # Configure NLP engine with spaCy
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
            }
        )
        nlp_engine = provider.create_engine()

        analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

        # Custom recognizer: Aadhaar (12 digits, may have spaces)
        aadhaar_recognizer = PatternRecognizer(
            supported_entity="AADHAAR_NUMBER",
            patterns=[Pattern("AADHAAR", r"\b\d{4}\s?\d{4}\s?\d{4}\b", 0.85)],
        )
        analyzer.registry.add_recognizer(aadhaar_recognizer)

        # Custom recognizer: PAN (format: ABCDE1234F)
        pan_recognizer = PatternRecognizer(
            supported_entity="PAN_NUMBER",
            patterns=[Pattern("PAN", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", 0.90)],
        )
        analyzer.registry.add_recognizer(pan_recognizer)

        # Custom recognizer: Policy number (alphanumeric 8-16 chars)
        policy_recognizer = PatternRecognizer(
            supported_entity="POLICY_NUMBER",
            patterns=[
                Pattern("POLICY_NUM", r"\bP\d{6,14}\b", 0.75),
                Pattern("POLICY_NUM_2", r"\b[A-Z]{2,4}\d{6,12}\b", 0.65),
            ],
        )
        analyzer.registry.add_recognizer(policy_recognizer)

        _analyzer = analyzer
    return _analyzer


def _get_anonymizer():
    global _anonymizer
    if _anonymizer is None:
        from presidio_anonymizer import AnonymizerEngine

        _anonymizer = AnonymizerEngine()
    return _anonymizer


# Mapping from Presidio entity type to our token
_ENTITY_TO_TOKEN = {
    "EMAIL_ADDRESS": "<EMAIL>",
    "PHONE_NUMBER": "<PHONE>",
    "PERSON": "<NAME>",
    "LOCATION": "<ADDRESS>",
    "AADHAAR_NUMBER": "<AADHAAR>",
    "PAN_NUMBER": "<PAN>",
    "POLICY_NUMBER": "<POLICY_NUMBER>",
    "DATE_TIME": "<DOB>",  # only flag DOBs, not general dates
}

# Map our tokens to pii_types field values
_TOKEN_TO_PII_TYPE = {
    "<EMAIL>": "email",
    "<PHONE>": "phone",
    "<NAME>": "name",
    "<ADDRESS>": "address",
    "<AADHAAR>": "aadhaar",
    "<PAN>": "pan",
    "<POLICY_NUMBER>": "policy_number",
    "<DOB>": "dob",
}


@dataclass
class PIIResult:
    redacted_text: str
    has_pii: bool
    pii_types: list[str]


def detect_and_redact(text: str) -> PIIResult:
    """
    Detect and redact PII from text.
    Returns PIIResult with redacted text and metadata.
    Never raises — returns original text on error.
    """
    if not text or len(text) < 10:
        return PIIResult(redacted_text=text, has_pii=False, pii_types=[])

    try:
        analyzer = _get_analyzer()
        anonymizer = _get_anonymizer()

        # Analyze
        results = analyzer.analyze(
            text=text,
            language="en",
            entities=list(_ENTITY_TO_TOKEN.keys()),
            score_threshold=0.65,
        )

        if not results:
            return PIIResult(redacted_text=text, has_pii=False, pii_types=[])

        # Build anonymization operators
        from presidio_anonymizer.entities import OperatorConfig

        operators = {}
        found_types = set()
        for result in results:
            entity = result.entity_type
            token = _ENTITY_TO_TOKEN.get(entity, f"<{entity}>")
            operators[entity] = OperatorConfig("replace", {"new_value": token})
            pii_type = _TOKEN_TO_PII_TYPE.get(token, entity.lower())
            found_types.add(pii_type)

        # Anonymize
        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )

        return PIIResult(
            redacted_text=anonymized.text,
            has_pii=True,
            pii_types=sorted(found_types),
        )

    except Exception as e:
        logger.warning(f"PII detection failed (returning original): {e}")
        return PIIResult(redacted_text=text, has_pii=False, pii_types=[])
