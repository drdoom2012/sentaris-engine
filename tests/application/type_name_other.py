"""A second module defining `Twin` exactly as `type_name_cases` does, so the two differ only by module (N9)."""

TypeNameCase = tuple[str, type, str, list[str]]


def type_name_cases(base: type) -> list[TypeNameCase]:
    """Build only `Twin` on `base`, with the qualname `type_name_cases.<locals>.Twin` of the other module's Twin."""

    class Twin(base):  # type: ignore[misc]
        pass

    return [("other-twin", Twin, f"{__name__}.type_name_cases.<locals>.Twin", [])]
