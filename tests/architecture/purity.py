"""Static checks over module sources: purity of pure code (DR-08), no Quasar code (DR-18), no exchange libraries (DR-19).

The checker sees only import statements and direct builtin calls in the source text (SE-1 spec, sections 6 and 9).
"""

import ast
from importlib.machinery import all_suffixes
from pathlib import Path

ROOT_PACKAGE = "sentaris_engine"
DOMAIN_PACKAGE = f"{ROOT_PACKAGE}.domain"
PURE_SUBPACKAGES: tuple[str, ...] = tuple(f"{ROOT_PACKAGE}.{name}" for name in ("domain", "application", "strategies"))

# Pinned by test_pinned_lists (SE-1 spec 6.1, 6.3); a change is a reviewed change of that test.
PURE_STDLIB: frozenset[str] = frozenset(
    {
        "__future__",
        "abc",
        "collections",
        "dataclasses",
        "decimal",
        "enum",
        "functools",
        "itertools",
        "math",
        "operator",
        "re",
        "types",
        "typing",
    }
)
FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {"open", "input", "print", "breakpoint", "__import__", "eval", "exec", "compile", "globals", "vars"}
)
BANNED_EVERYWHERE: frozenset[str] = frozenset(
    {
        "quasar_market_data",
        "ccxt",
        "binance",
        "pybit",
        "okx",
        "kucoin",
        "krakenex",
        "coinbase",
        "cryptofeed",
        "freqtrade",
        "hummingbot",
    }
)
KNOWN_CHILDREN: frozenset[str] = frozenset({"domain", "application", "strategies", "infrastructure"})


def _is_under(name: str, prefix: str) -> bool:
    """True if `name` is `prefix` or below it, matching whole dotted components."""
    return name == prefix or name.startswith(prefix + ".")


def _allowed_internal(module: str) -> tuple[str, ...] | None:
    """Internal prefixes a pure module may import; None if the module is not pure (SE-1 spec 5.2, 6.1)."""
    if module == ROOT_PACKAGE:
        return ()
    for subpackage in PURE_SUBPACKAGES:
        if _is_under(module, subpackage):
            return tuple(sorted({subpackage, DOMAIN_PACKAGE}))
    return None


def _resolve(node: ast.Import | ast.ImportFrom, package: str) -> list[str] | None:
    """Absolute names an import statement brings in; None if a relative import goes above the top-level package."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.level == 0:
        base = node.module or ""
    else:
        parts = package.split(".") if package else []
        keep = len(parts) - (node.level - 1)
        if keep <= 0:
            return None
        base = ".".join(parts[:keep])
        if node.module:
            base = f"{base}.{node.module}"
    if _is_under(base, ROOT_PACKAGE):
        return [f"{base}.{alias.name}" for alias in node.names]
    return [base]


def find_violations(module: str, *, is_package: bool, source: str) -> list[str]:
    """One human-readable string per violation of DR-08 (pure modules), DR-18 and DR-19 (every module)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as error:
        return [f"{module}: source does not parse ({type(error).__name__})"]

    package = module if is_package else module.rpartition(".")[0]
    allowed_internal = _allowed_internal(module)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            where = f"{module}:{node.lineno}"
            names = _resolve(node, package)
            if names is None:
                violations.append(f"{where}: relative import goes above the top-level package")
                continue
            for name in names:
                top_level = name.partition(".")[0]
                if top_level in BANNED_EVERYWHERE:
                    violations.append(f"{where}: import of {name} is banned (DR-18, DR-19)")
                elif allowed_internal is None:
                    continue
                elif top_level == ROOT_PACKAGE:
                    if not any(_is_under(name, prefix) for prefix in allowed_internal):
                        violations.append(f"{where}: internal import of {name} not allowed here (DR-08)")
                elif top_level not in PURE_STDLIB:
                    violations.append(f"{where}: import of {name} not allowed in pure code (DR-08)")
        elif (
            allowed_internal is not None
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FORBIDDEN_CALLS
        ):
            violations.append(f"{module}:{node.lineno}: call of {node.func.id}() not allowed in pure code (DR-08)")
    return violations


def unknown_children(package_dir: Path) -> list[str]:
    """Sorted names of importable direct children of `package_dir` that are not in KNOWN_CHILDREN."""
    importable_suffixes = set(all_suffixes())
    unknown: list[str] = []
    for child in package_dir.iterdir():
        if child.is_dir():
            if child.name != "__pycache__" and child.name not in KNOWN_CHILDREN:
                unknown.append(child.name)
        elif child.suffix in importable_suffixes and child.name != "__init__.py":
            unknown.append(child.name)
    return sorted(unknown)


def module_name(path: Path, root: Path) -> tuple[str, bool]:
    """Qualified module name and whether it is a package, for a `.py` file under `root`."""
    parts = path.relative_to(root).with_suffix("").parts
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False
