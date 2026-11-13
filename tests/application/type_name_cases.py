"""The N9 classes of the type-name tests, built on a given base (`object` or `Exception`).

Each case is `(case id, class, expected name, log)`. A log records every hostile method that ran and must stay
empty. Every class is created inside `type_name_cases`, so its real qualname starts with
`type_name_cases.<locals>.`; expected names are spelled from this module's `__name__` and that qualname,
except the cases that set or lack a module, which do not depend on `__name__`.
"""

from typing import Any

TypeNameCase = tuple[str, type, str, list[str]]

_NAMES = frozenset({"__name__", "__qualname__", "__module__"})
_LOCALS = f"{__name__}.type_name_cases.<locals>"


def _exec_class(base: type, name: str) -> type:
    """Create a class with `type(...)` under globals that hold no `__name__`, so no `__module__` is recorded."""
    namespace: dict[str, Any] = {"base": base}
    exec(f'C = type("{name}", (base,), {{}})', namespace)  # noqa: S102  # the U9 case needs globals without __name__
    created: type = namespace["C"]
    return created


def type_name_cases(base: type) -> list[TypeNameCase]:
    """Build the N9 classes on `base`; nothing of them is touched while building."""
    cases: list[TypeNameCase] = []

    class Outer(base):  # type: ignore[misc]
        class Inner(base):  # type: ignore[misc]
            pass

    cases.append(("nested", Outer.Inner, f"{_LOCALS}.Outer.Inner", []))

    class Twin(base):  # type: ignore[misc]
        pass

    cases.append(("twin", Twin, f"{_LOCALS}.Twin", []))

    raising_log: list[str] = []

    class RaisingMeta(type):
        def __getattribute__(cls, name: str) -> Any:
            if name in _NAMES:
                raising_log.append(name)
                raise AssertionError("metaclass attribute read")
            return super().__getattribute__(name)

    class MetaRaises(base, metaclass=RaisingMeta):  # type: ignore[misc]
        pass

    cases.append(("metaclass-raises", MetaRaises, f"{_LOCALS}.MetaRaises", raising_log))

    lying_log: list[str] = []

    class LyingMeta(type):
        @property
        def __name__(cls) -> str:  # type: ignore[override]
            lying_log.append("property __name__")
            return "Lie"

        @property
        def __module__(cls) -> str:  # type: ignore[override]
            lying_log.append("property __module__")
            return "lie"

        def __getattribute__(cls, name: str) -> Any:
            if name in _NAMES:
                lying_log.append(name)
                return "lie"
            return super().__getattribute__(name)

    class MetaLies(base, metaclass=LyingMeta):  # type: ignore[misc]
        pass

    cases.append(("metaclass-lies", MetaLies, f"{_LOCALS}.MetaLies", lying_log))

    qualname_log: list[str] = []

    class LoggingQualname(str):
        def __add__(self, other: str) -> str:
            qualname_log.append("__add__")
            return "lie"

        def __radd__(self, other: str) -> str:
            qualname_log.append("__radd__")
            return "lie"

        def __str__(self) -> str:
            qualname_log.append("__str__")
            return "lie"

    class QualnameSet(base):  # type: ignore[misc]
        pass

    QualnameSet.__qualname__ = LoggingQualname("Fancy")
    cases.append(("qualname-str-subclass", QualnameSet, f"{__name__}.Fancy", qualname_log))

    module_log: list[str] = []

    class LoggingModule(str):
        def __len__(self) -> int:
            module_log.append("__len__")
            return 0

        def __bool__(self) -> bool:
            module_log.append("__bool__")
            return False

        def __eq__(self, other: object) -> bool:
            module_log.append("__eq__")
            return False

        def __hash__(self) -> int:
            module_log.append("__hash__")
            return 0

        def __str__(self) -> str:
            module_log.append("__str__")
            return "lie"

    class ModuleSubclass(base):  # type: ignore[misc]
        __module__ = LoggingModule("mymod")

    cases.append(("module-str-subclass", ModuleSubclass, "mymod.type_name_cases.<locals>.ModuleSubclass", module_log))

    class ModuleInt(base):  # type: ignore[misc]
        __module__ = 42  # type: ignore[assignment]

    cases.append(("module-int", ModuleInt, "type_name_cases.<locals>.ModuleInt", []))

    class ModuleProperty(base):  # type: ignore[misc]
        __module__ = property(lambda self: "lie")

    cases.append(("module-property", ModuleProperty, "type_name_cases.<locals>.ModuleProperty", []))

    class ModuleEmpty(base):  # type: ignore[misc]
        __module__ = ""

    cases.append(("module-empty", ModuleEmpty, "type_name_cases.<locals>.ModuleEmpty", []))

    cases.append(("module-absent", _exec_class(base, "C"), "C", []))
    cases.append(("module-absent-empty-qualname", _exec_class(base, ""), "", []))

    if base is Exception:
        cases.append(("builtin-ValueError", ValueError, "builtins.ValueError", []))
    else:
        cases.append(("builtin-NoneType", type(None), "builtins.NoneType", []))

    return cases
