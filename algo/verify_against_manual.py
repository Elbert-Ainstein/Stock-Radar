#!/usr/bin/env python3
"""Static check of a platform strategy against the broker's API manual.

WHY THIS EXISTS: the first version of settled_basis_ladder.py was verified for
function NAMES and ENUM MEMBERS only, and shipped with seven editor errors —
`round(x, 2)` (the platform's round takes ONE argument) and an int literal
passed where `min()` demands a float. Checking that a name exists proves
nothing about how it is called. This checks the call itself.

What it verifies, per call site:
  1. the function is documented in the manual;
  2. positional arity does not exceed the documented parameter count;
  3. keyword names are all documented parameters;
  4. arguments to the strict float helpers (min/max/abs/floor/ceil/round) are
     not int LITERALS — the editor type-checks those and rejects `min(x, 0)`.

Usage:
    python3 algo/verify_against_manual.py <strategy.py> <manual.md>

Exit code 1 on any violation, so it can gate a commit.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Documented as taking float arguments; the editor rejects int literals here.
STRICT_FLOAT = {"min", "max", "abs", "floor", "ceil", "round", "power",
                "mod", "integer_division", "rate_ratio", "math_log"}

# Names that are Python builtins/locals rather than platform API.
IGNORE = {"range", "len", "str", "int", "float", "bool", "list", "dict", "set",
          "tuple", "sorted", "sum", "enumerate", "zip", "getattr", "isinstance",
          "super", "Exception", "type", "repr",
          # framework constructors documented as prose, not as an API entry
          "Contract"}


def parse_manual(manual_path: Path) -> dict[str, dict]:
    """Extract {function: {params: [...], required: n}} from the manual's
    `## fn` sections and their first fenced signature line."""
    text = manual_path.read_text(encoding="utf-8")
    api: dict[str, dict] = {}
    for m in re.finditer(r"^## ([a-z_][a-z0-9_]*)\s*$", text, re.M):
        name = m.group(1)
        section = text[m.end(): m.end() + 2500]
        sig = re.search(r"```\s*\n\s*" + re.escape(name) + r"\((.*?)\)\s*\n```",
                        section, re.S)
        if not sig:
            api.setdefault(name, {"params": None, "required": 0})
            continue
        raw = sig.group(1).strip()
        params, required, varargs = [], 0, False
        if raw:
            for part in re.split(r",(?![^\[\]{}()]*\))", raw):
                part = part.strip()
                if not part:
                    continue
                if part.startswith("*"):
                    varargs = True
                    continue
                pname = part.split("=")[0].strip()
                params.append(pname)
                if "=" not in part:
                    required += 1
        api[name] = {"params": params, "required": required, "varargs": varargs}

    # Second pass: some framework functions are documented only inside fenced
    # code (declare_trig_symbol) or under a prose heading ("How to use the
    # function show_variable()"). Harvest any line in a code block that LOOKS
    # like a signature — every parameter an identifier or identifier=default.
    # An example CALL such as min(0,1,2,3) fails that test and is ignored,
    # which is what keeps this from inventing APIs out of examples.
    ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    for block in re.findall(r"```(.*?)```", text, re.S):
        for line in block.splitlines():
            m2 = re.match(r"^\s*(?:[\w.]+\s*=\s*)?([a-z_][a-z0-9_]*)\((.*)\)\s*$", line)
            if not m2:
                continue
            name, raw = m2.group(1), m2.group(2).strip()
            if name in api:
                continue
            params, required, ok = [], 0, True
            if raw:
                for part in raw.split(","):
                    pname = part.split("=")[0].strip()
                    if not ident.match(pname):
                        ok = False
                        break
                    params.append(pname)
                    if "=" not in part:
                        required += 1
            if ok:
                api[name] = {"params": params, "required": required, "varargs": False}
    return api


def check(strategy_path: Path, manual_path: Path) -> list[str]:
    api = parse_manual(manual_path)
    src = strategy_path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    local = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    problems: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # self.foo(...) is a method on the strategy, not platform API
        if isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        name = node.func.id
        if name in IGNORE or name in local:
            continue

        spec = api.get(name)
        if spec is None:
            problems.append(f"L{node.lineno}: {name}() is not documented in the manual")
            continue
        params = spec.get("params")

        # int literals where the editor demands float. The editor INFERS the
        # type, so it rejects `min(x, total_cash(...) or 0)` too — the `or 0`
        # branch is an int. So look inside the argument expression, not just
        # at a bare literal. (This is the line-334 error class.)
        if name in STRICT_FLOAT:
            for i, arg in enumerate(node.args, 1):
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, int) \
                            and not isinstance(sub.value, bool):
                        where = ("is the int literal" if sub is arg
                                 else "contains the int literal")
                        problems.append(
                            f"L{node.lineno}: {name}() arg {i} {where} "
                            f"{sub.value} — the editor infers int and demands "
                            f"float (use {sub.value}.0)")
                        break

        if params is None:
            continue
        if not spec.get("varargs") and len(node.args) > len(params):
            problems.append(
                f"L{node.lineno}: {name}() called with {len(node.args)} positional "
                f"args but the manual documents {len(params)}: ({', '.join(params)})")
        for kw in node.keywords:
            if kw.arg and kw.arg not in params:
                problems.append(
                    f"L{node.lineno}: {name}() has no parameter '{kw.arg}' "
                    f"(documented: {', '.join(params)})")
    # ── type-inference taint: `x = f(...) or 0` makes x int-typed to the
    #    editor, so a LATER `min(y, x)` is rejected even though the call site
    #    itself contains no literal. That is the line-334 error class, which a
    #    call-site-local check cannot see. Two passes: find int-tainted names,
    #    then find strict-float calls that consume them.
    tainted: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.BoolOp):
            for v in node.value.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, int) \
                        and not isinstance(v.value, bool):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            tainted[tgt.id] = node.lineno
    if tainted:
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in STRICT_FLOAT:
                continue
            for i, arg in enumerate(node.args, 1):
                if isinstance(arg, ast.Name) and arg.id in tainted:
                    problems.append(
                        f"L{node.lineno}: {node.func.id}() arg {i} is '{arg.id}', "
                        f"which L{tainted[arg.id]} defaults to an int literal — "
                        f"the editor infers int here and demands float")

    return problems


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    strategy, manual = Path(sys.argv[1]), Path(sys.argv[2])
    problems = check(strategy, manual)
    if problems:
        print("VIOLATIONS (" + str(len(problems)) + "):")
        for p in problems:
            print("  " + p)
        return 1
    print("clean — every call matches the manual's documented signature")
    return 0


if __name__ == "__main__":
    sys.exit(main())
