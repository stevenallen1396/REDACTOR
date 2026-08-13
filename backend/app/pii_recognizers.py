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

# spaCy's NER (particularly en_core_web_sm, used in the hosted deployment to fit its
# memory budget) misses a lot of real names: honorific-introduced ones ("Dear Mr
# Thompson") especially, since without this pattern the model has to recognise the
# name from capitalisation alone. Catching the honorific+name pattern directly is
# far more reliable than hoping the statistical model generalises to it.
HONORIFIC_NAME_RECOGNIZER = PatternRecognizer(
    supported_entity="PERSON",
    name="HonorificNameRecognizer",
    patterns=[
        Pattern(
            name="honorific_prefixed_name",
            regex=r"(?i)\b(?:mr|mrs|ms|miss|mx|dr|prof|sir|dame|rev)\.?\s+[a-z][a-z'\-]*(?:\s+[a-z][a-z'\-]*){0,2}\b",
            score=0.85,
        )
    ],
)

# No NER model tags job titles out of the box (spaCy's built-in entity types don't
# include one) - this is a plain curated word/phrase list instead. Necessarily
# incomplete, but covers common UK business/office/automotive-trade titles; add more
# to the list below as needed. Ordered longest-phrase-first so e.g. "Managing
# Director" is caught whole rather than leaving "Managing" behind.
_JOB_TITLES = [
    "Chief Executive Officer", "Chief Financial Officer", "Chief Operating Officer",
    "Chief Technology Officer", "Managing Director", "Non-Executive Director",
    "Executive Director", "Financial Controller", "Human Resources Manager",
    "Operations Manager", "General Manager", "Regional Manager", "Branch Manager",
    "Assistant Manager", "Deputy Manager", "Workshop Manager", "Service Manager",
    "Service Advisor", "Sales Manager", "Sales Executive", "Account Manager",
    "Marketing Manager", "Marketing Executive", "Customer Service Manager",
    "Business Manager", "Finance Manager", "Finance Director", "Parts Advisor",
    "Dealer Principal", "Team Leader", "Managing Partner",
    "CEO", "CFO", "COO", "CTO", "HR Manager",
    "Director", "Chairman", "Chairwoman", "Chairperson", "President",
    "Vice President", "Partner", "Proprietor", "Manager", "Supervisor",
    "Coordinator", "Administrator", "Secretary", "Receptionist", "Consultant",
    "Analyst", "Engineer", "Technician", "Mechanic", "Solicitor", "Accountant",
]
JOB_TITLE_RECOGNIZER = PatternRecognizer(
    supported_entity="JOB_TITLE",
    name="JobTitleRecognizer",
    patterns=[
        Pattern(
            name="job_title",
            regex=r"(?i)\b(?:" + "|".join(_JOB_TITLES) + r")\b",
            score=0.6,
        )
    ],
)

CUSTOM_RECOGNIZERS = [
    UK_POSTCODE_RECOGNIZER,
    UK_NINO_RECOGNIZER,
    UK_PHONE_RECOGNIZER,
    HONORIFIC_NAME_RECOGNIZER,
    JOB_TITLE_RECOGNIZER,
]
