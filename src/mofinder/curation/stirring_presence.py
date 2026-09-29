"""Three-state stirring annotation for the nine-field process control.

Use the audited source interpretation, including DOI-scoped clarifications.
An explicit static synthesis takes precedence over preparation-stage stirring.
When the later stage is unspecified, reported preparation stirring counts as yes.
"""
from .process_stirring import method_name, normalize_stirring

STIRRING_VALUES = ("yes", "no", "not reported")
STIRRING_PRESENCE_VERSION = "stirring-presence-v1"


def classify_stirring(value, doi=""):
    """Return the ternary value, decision, and existing detailed interpretation."""
    parsed = normalize_stirring(value, doi)
    detail = parsed["detailed_value"]
    if detail == "Static / no stirring" or detail.endswith(" before static synthesis"):
        state, decision = "no", "explicit_static_or_unstirred_synthesis"
    elif detail.startswith("Stirred"):
        state, decision = "yes", "stirring_reported_without_explicit_static_synthesis"
    elif detail in ("Not reported", "Unclear / ambiguous"):
        state, decision = "not reported", "missing_or_ambiguous_stirring_state"
    elif (not parsed["rule"].startswith("source_review:")
          and method_name(parsed["normalized_text"]) == "Stirred"):
        # The eleven-field profile gives rotation priority over a separate
        # prestir. This field records that supported stirring mention as well.
        state, decision = "yes", "stirring_reported_alongside_another_method"
    else:
        # Includes source-reviewed ultrasonic wording: 'ultrasonically stirred'
        # was verified as sonication, without separate mechanical stirring.
        state, decision = "not reported", "other_method_does_not_establish_stirring"
    return {"stirring": state, "decision": decision,
            "agitation": parsed["value"], "detailed_agitation": detail,
            "source_rule": parsed["rule"]}
