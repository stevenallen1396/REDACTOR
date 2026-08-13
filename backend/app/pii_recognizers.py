"""UK-specific PII recognizers not covered by Presidio's built-in (US-centric) set."""

from presidio_analyzer import Pattern, PatternRecognizer

UK_POSTCODE_RECOGNIZER = PatternRecognizer(
    supported_entity="UK_POSTCODE",
    name="UkPostcodeRecognizer",
    patterns=[
        Pattern(
            name="uk_postcode",
            regex=r"\b[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}\b",
            score=0.7,
        )
    ],
)

UK_NINO_RECOGNIZER = PatternRecognizer(
    supported_entity="UK_NINO",
    name="UkNinoRecognizer",
    patterns=[
        Pattern(
            name="uk_national_insurance_number",
            # Two letters, six digits (optionally grouped), one letter suffix (A-D).
            # Deliberately permissive on the letter prefix (favouring recall over
            # strict validity) since missing a real NINO is worse than a rare false hit.
            regex=r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
            score=0.85,
        )
    ],
)

UK_PHONE_RECOGNIZER = PatternRecognizer(
    supported_entity="UK_PHONE_NUMBER",
    name="UkPhoneRecognizer",
    patterns=[
        Pattern(
            name="uk_phone_number",
            regex=r"\b(?:\+44\s?7\d{3}|\(?07\d{3}\)?)\s?\d{3}\s?\d{3}\b",
            score=0.6,
        )
    ],
)

CUSTOM_RECOGNIZERS = [UK_POSTCODE_RECOGNIZER, UK_NINO_RECOGNIZER, UK_PHONE_RECOGNIZER]
