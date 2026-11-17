"""Executable architecture constraints for the two-service and model boundaries.

These checks catch ordinary imports, direct database opens, and provider initialization;
they are a maintainability guard, not a sandbox against deliberately obfuscated Python.
"""

import ast
import os
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "platform_app"
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".sh", ".bat"}
IGNORED_DIRECTORIES = {".venv", "node_modules", "dist", "__pycache__", ".cache", ".git"}
PROVIDER_CONSTRUCTORS = {
    "init_chat_model", "ChatOpenAI", "AzureChatOpenAI", "ChatAnthropic",
    "ChatGoogleGenerativeAI", "ChatVertexAI", "ChatBedrock", "ChatBedrockConverse",
    "ChatOllama", "OpenAI", "AsyncOpenAI", "AzureOpenAI", "AsyncAzureOpenAI",
    "Anthropic", "AsyncAnthropic",
}


def platform_trees():
    files = sorted(PLATFORM.rglob("*.py"))
    assert files, "The platform source directory must exist for boundary checks."
    return [(path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))) for path in files]


def label(path, node, reason):
    return f"{path.relative_to(ROOT)}:{node.lineno}: {reason}"


def qualified_name(node, imports):
    if isinstance(node, ast.Name):
        return imports.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{qualified_name(node.value, imports)}.{node.attr}"
    return ""


def import_bindings(tree):
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bindings


def test_platform_never_imports_commerce_implementation():
    """FR-003/NFR-031: the service boundary is HTTP, not a Python import."""
    violations = []
    for path, tree in platform_trees():
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            elif isinstance(node, ast.Call) and qualified_name(node.func, {}) in {
                "__import__", "importlib.import_module",
            }:
                modules = [arg.value for arg in node.args if isinstance(arg, ast.Constant)
                           and isinstance(arg.value, str)]
            for module in modules:
                if module == "commerce" or module.startswith("commerce."):
                    violations.append(label(path, node, f"illegal Commerce implementation import: {module}"))
    assert not violations, "\n".join(violations)


def references_commerce_db(node, assigned, visited=frozenset()):
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if re.search(r"commerce\.db(?:\b|$)", child.value, re.IGNORECASE):
                return True
        if isinstance(child, (ast.Name, ast.Attribute)):
            name = child.id if isinstance(child, ast.Name) else child.attr
            if "commerce_db" in name.lower():
                return True
            if name in assigned and name not in visited:
                if references_commerce_db(assigned[name], assigned, visited | {name}):
                    return True
    return False


def test_platform_never_opens_commerce_database():
    """FR-003: do not turn shared local storage into a hidden integration path."""
    violations = []
    for path, tree in platform_trees():
        assigned = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned[target.id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
                assigned[node.target.id] = node.value
        imports = import_bindings(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = qualified_name(node.func, imports)
            operation = name.rsplit(".", 1)[-1]
            if operation not in {"connect", "open", "read_text", "read_bytes", "execute", "executescript"}:
                continue
            targets = [*node.args, *(keyword.value for keyword in node.keywords)]
            if isinstance(node.func, ast.Attribute):
                targets.append(node.func.value)
            if any(references_commerce_db(target, assigned) for target in targets):
                violations.append(label(path, node, f"illegal Commerce database access via {name}"))
    assert not violations, "\n".join(violations)


def test_provider_chat_calls_require_the_single_grounded_wrapper():
    """FR-043/072: no provider calls are allowed in this foundation without GroundedLLM."""
    trees = platform_trees()
    wrappers = [path for path, tree in trees if any(
        isinstance(node, ast.ClassDef) and node.name == "GroundedLLM" for node in ast.walk(tree)
    )]
    assert len(wrappers) <= 1, "GroundedLLM must have one implementation, not alternative entry points."
    if wrappers:
        assert wrappers[0].parent == PLATFORM / "llm", "GroundedLLM belongs in platform_app/llm/."
    violations = []
    for path, tree in trees:
        if path in wrappers:
            continue
        imports = import_bindings(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = qualified_name(node.func, imports)
            terminal = name.rsplit(".", 1)[-1]
            direct_provider = terminal in PROVIDER_CONSTRUCTORS or name in {
                "litellm.completion", "litellm.acompletion", "openai.ChatCompletion.create",
                "openai.ChatCompletion.acreate", "google.generativeai.GenerativeModel",
            }
            endpoint = any(isinstance(value, ast.Constant) and isinstance(value.value, str)
                           and ("/chat/completions" in value.value
                                or "generativelanguage.googleapis.com" in value.value)
                           for arg in [*node.args, *(keyword.value for keyword in node.keywords)]
                           for value in ast.walk(arg))
            raw_chat = name.endswith((".chat.completions.create", ".messages.create", ".generate_content"))
            if direct_provider or endpoint or raw_chat:
                violations.append(label(path, node, f"model call bypasses GroundedLLM: {name}"))
    assert not violations, "\n".join(violations)


def test_implementation_code_files_stay_within_400_lines():
    """NFR-030: documentation is excluded; implementation and tests share the code ceiling."""
    # Prune dependency/cache trees before walking them. Filtering only after rglob
    # still enumerates tens of thousands of ignored files on native Windows.
    files = []
    for directory, children, names in os.walk(ROOT):
        children[:] = [name for name in children if name not in IGNORED_DIRECTORIES]
        files.extend(Path(directory) / name for name in names if Path(name).suffix in CODE_EXTENSIONS)
    oversized = [(str(path.relative_to(ROOT)), len(path.read_text(encoding="utf-8").splitlines()))
                 for path in files if len(path.read_text(encoding="utf-8").splitlines()) > 400]
    assert not oversized, f"Split implementation files above 400 lines: {oversized}"
