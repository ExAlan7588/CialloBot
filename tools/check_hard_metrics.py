from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import TypeAlias

MAX_FILE_LINES = 600
MAX_FUNCTION_LINES = 50
MAX_POSITIONAL_PARAMS = 3
MAX_NESTING_DEPTH = 3
MAX_COMPLEXITY = 10

EXCLUDED_PARTS = {".git", ".venv", ".codex-tasks", "__pycache__"}
NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
    ast.ExceptHandler,
)
BRANCH_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.ExceptHandler,
    ast.IfExp,
    ast.BoolOp,
    ast.Match,
)

FunctionNode: TypeAlias = ast.FunctionDef | ast.AsyncFunctionDef
ViolationList: TypeAlias = list[str]


def main() -> int:
    violations: ViolationList = []
    for path in _python_files():
        violations.extend(_file_violations(path))

    if violations:
        sys.stderr.write("\n".join(violations))
        sys.stderr.write("\n")
        return 1

    sys.stdout.write("Hard metrics scan passed\n")
    return 0


def _python_files() -> list[Path]:
    return sorted(
        path
        for path in Path().rglob("*.py")
        if not any(part in EXCLUDED_PARTS for part in path.parts)
    )


def _file_violations(path: Path) -> ViolationList:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    violations: ViolationList = []
    if len(lines) > MAX_FILE_LINES:
        violations.append(f"{path}: file has {len(lines)} lines > {MAX_FILE_LINES}")

    tree = ast.parse(text, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_function_violations(path, lines, node))
    return violations


def _function_violations(path: Path, lines: list[str], node: FunctionNode) -> ViolationList:
    checks = (
        _line_count_violation(path, lines, node),
        _parameter_violation(path, node),
        _nesting_violation(path, node),
        _complexity_violation(path, node),
    )
    return [violation for violation in checks if violation is not None]


def _line_count_violation(path: Path, lines: list[str], node: FunctionNode) -> str | None:
    line_count = _non_blank_lines(lines, node.lineno, node.end_lineno or node.lineno)
    if line_count <= MAX_FUNCTION_LINES:
        return None
    return f"{path}:{node.lineno}: {node.name} has {line_count} non-blank lines"


def _non_blank_lines(lines: list[str], start: int, end: int) -> int:
    return sum(1 for line in lines[start - 1 : end] if line.strip())


def _parameter_violation(path: Path, node: FunctionNode) -> str | None:
    count = len(node.args.posonlyargs) + len(node.args.args)
    if count <= MAX_POSITIONAL_PARAMS:
        return None
    return f"{path}:{node.lineno}: {node.name} has {count} positional params"


def _nesting_violation(path: Path, node: FunctionNode) -> str | None:
    depth = _max_nesting_depth(node)
    if depth <= MAX_NESTING_DEPTH:
        return None
    return f"{path}:{node.lineno}: {node.name} nesting depth {depth}"


def _max_nesting_depth(node: ast.AST) -> int:
    return max((_nesting_depth(child, 0) for child in ast.iter_child_nodes(node)), default=0)


def _nesting_depth(node: ast.AST, depth: int) -> int:
    current_depth = depth + 1 if isinstance(node, NESTING_NODES) else depth
    child_depths = (_nesting_depth(child, current_depth) for child in ast.iter_child_nodes(node))
    return max(child_depths, default=current_depth)


def _complexity_violation(path: Path, node: FunctionNode) -> str | None:
    score = _complexity(node)
    if score <= MAX_COMPLEXITY:
        return None
    return f"{path}:{node.lineno}: {node.name} complexity {score}"


def _complexity(node: ast.AST) -> int:
    return 1 + sum(_complexity_increment(child) for child in ast.walk(node))


def _complexity_increment(node: ast.AST) -> int:
    if isinstance(node, ast.BoolOp):
        return max(1, len(node.values) - 1)
    if isinstance(node, ast.Try):
        return len(node.handlers) + bool(node.orelse) + bool(node.finalbody)
    if isinstance(node, ast.Match):
        return len(node.cases)
    if isinstance(node, BRANCH_NODES):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
