"""The instrument key: an opaque non-empty string (domain section 6.8)."""

from sentaris_engine.domain.errors import EvaluationTypeError


def check_instrument_key(value: object) -> str:
    """Return `value` if it is a non-empty exact `str`; no format and no surrogate rule (section 6.8)."""
    if type(value) is not str or not value:
        raise EvaluationTypeError("instrument key is not a non-empty exact str (section 6.8)")
    return value
