"""The construction error of the evaluation types (SE-3 spec 5, "Errors")."""


class EvaluationTypeError(ValueError):
    """Malformed input to an evaluation type or validator; distinct from `PayloadError`.

    Only the class is meaningful; a message is never reported (domain section 6.7).
    """
