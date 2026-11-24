"""Minimal Call of Duty: World at War 1.7 GSC subset evaluator and fake dvar store.

Parses and executes actual `.gsc` files from `mod/` directly so offline contract
tests exercise the real scripts compiled into `mod.ff` rather than a duplicate
Python reimplementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


class _UndefinedType:
    def __repr__(self) -> str:
        return "undefined"

    def __bool__(self) -> bool:
        return False


UNDEFINED = _UndefinedType()


class GscSyntaxError(SyntaxError):
    """Raised when a GSC script contains syntax unsupported by WaW 1.7."""


class GscRuntimeError(RuntimeError):
    """Raised when a GSC script triggers a runtime error."""


class GscStruct:
    """Equivalent of a WaW GSC struct returned by SpawnStruct()."""

    def __init__(self) -> None:
        self._fields: dict[str, Any] = {}

    def get_field(self, name: str) -> Any:
        return self._fields.get(name.lower(), UNDEFINED)

    def set_field(self, name: str, value: Any) -> None:
        self._fields[name.lower()] = value

    def to_dict(self) -> dict[str, Any]:
        return dict(self._fields)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get_field(name)

    def __repr__(self) -> str:
        return f"GscStruct({self._fields!r})"


class GscArray:
    """Equivalent of a WaW GSC array (indexed or associative) with `.size`."""

    def __init__(self, items: list[Any] | None = None) -> None:
        self._data: dict[Any, Any] = {}
        if items:
            for idx, val in enumerate(items):
                self._data[idx] = val

    @property
    def size(self) -> int:
        return len(self._data)

    def get_item(self, key: Any) -> Any:
        return self._data.get(key, UNDEFINED)

    def set_item(self, key: Any, value: Any) -> None:
        self._data[key] = value

    def to_list(self) -> list[Any]:
        return [self._data[i] for i in range(len(self._data))]

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, key: Any) -> Any:
        return self.get_item(key)

    def __repr__(self) -> str:
        return f"GscArray({self._data!r})"


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Token:
    kind: str
    value: Any
    line: int


KEYWORDS = {
    "if",
    "else",
    "for",
    "while",
    "return",
    "true",
    "false",
    "undefined",
    "break",
    "continue",
}

FORBIDDEN_WAW17_KEYWORDS = {"foreach"}

TWO_CHAR_OPS = {
    "==",
    "!=",
    "<=",
    ">=",
    "&&",
    "||",
    "+=",
    "-=",
    "*=",
    "/=",
    "++",
    "--",
    "::",
}

SINGLE_CHAR_OPS = set("+-*/%<>=!.,;(){}[]")


def tokenize(source: str, filename: str = "<gsc>") -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(source)
    line = 1

    while i < n:
        ch = source[i]

        # Whitespace
        if ch in " \t\r":
            i += 1
            continue
        if ch == "\n":
            line += 1
            i += 1
            continue

        # Line comment //
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            i += 2
            while i < n and source[i] != "\n":
                i += 1
            continue

        # Block comment /* ... */
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                if source[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue

        # String literal
        if ch == '"':
            start_line = line
            i += 1
            chars: list[str] = []
            while i < n and source[i] != '"':
                if source[i] == "\\":
                    i += 1
                    if i >= n:
                        raise GscSyntaxError(f"{filename}:{start_line}: unterminated string escape")
                    esc = source[i]
                    escape_map = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                    chars.append(escape_map.get(esc, esc))
                    i += 1
                else:
                    if source[i] == "\n":
                        line += 1
                    chars.append(source[i])
                    i += 1
            if i >= n:
                raise GscSyntaxError(f"{filename}:{start_line}: unterminated string literal")
            i += 1  # closing quote
            tokens.append(Token("STRING", "".join(chars), start_line))
            continue

        # Number literal (int or float)
        if ch.isdigit() or (ch == "." and i + 1 < n and source[i + 1].isdigit()):
            start = i
            is_float = False
            while i < n and source[i].isdigit():
                i += 1
            if i < n and source[i] == ".":
                is_float = True
                i += 1
                while i < n and source[i].isdigit():
                    i += 1
            raw = source[start:i]
            tokens.append(Token("NUMBER", float(raw) if is_float else int(raw), line))
            continue

        # Identifier or module path (e.g. maps\_gauntlet_rules)
        if ch.isalpha() or ch == "_":
            start = i
            while i < n and (source[i].isalnum() or source[i] in "_\\"):
                i += 1
            word = source[start:i]
            lower = word.lower()
            if lower in FORBIDDEN_WAW17_KEYWORDS:
                raise GscSyntaxError(
                    f"{filename}:{line}: '{word}' is not valid in CoD:WaW 1.7 GSC; use an indexed for-loop"
                )
            if lower in KEYWORDS:
                tokens.append(Token(lower.upper(), lower, line))
            else:
                tokens.append(Token("IDENT", word, line))
            continue

        # Two-character operators
        if i + 1 < n and source[i : i + 2] in TWO_CHAR_OPS:
            op = source[i : i + 2]
            tokens.append(Token(op, op, line))
            i += 2
            continue

        # Single-character operators
        if ch in SINGLE_CHAR_OPS:
            tokens.append(Token(ch, ch, line))
            i += 1
            continue

        raise GscSyntaxError(f"{filename}:{line}: unexpected character {ch!r}")

    tokens.append(Token("EOF", None, line))
    return tokens


# ---------------------------------------------------------------------------
# AST Nodes
# ---------------------------------------------------------------------------

@dataclass
class FunctionDef:
    name: str
    params: list[str]
    body: BlockStmt
    line: int


@dataclass
class BlockStmt:
    statements: list[Any]


@dataclass
class IfStmt:
    cond: Any
    then_branch: Any
    else_branch: Any | None


@dataclass
class ForStmt:
    init: Any | None
    cond: Any | None
    step: Any | None
    body: Any


@dataclass
class WhileStmt:
    cond: Any
    body: Any


@dataclass
class ReturnStmt:
    value: Any | None


@dataclass
class BreakStmt:
    pass


@dataclass
class ContinueStmt:
    pass


@dataclass
class ExprStmt:
    expr: Any


@dataclass
class AssignExpr:
    target: Any
    op: str
    value: Any


@dataclass
class PostfixUpdateExpr:
    target: Any
    op: str  # "++" or "--"


@dataclass
class BinaryExpr:
    op: str
    left: Any
    right: Any


@dataclass
class UnaryExpr:
    op: str
    operand: Any


@dataclass
class CallExpr:
    module_path: str | None
    func_name: str
    args: list[Any]
    line: int


@dataclass
class FieldAccess:
    obj: Any
    field: str


@dataclass
class IndexAccess:
    obj: Any
    index: Any


@dataclass
class VarRef:
    name: str


@dataclass
class Literal:
    value: Any


@dataclass
class ArrayLiteral:
    pass


# ---------------------------------------------------------------------------
# Recursive-Descent Parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens: list[Token], filename: str) -> None:
        self.tokens = tokens
        self.pos = 0
        self.filename = filename

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def match(self, *kinds: str) -> Token | None:
        tok = self.peek()
        if tok.kind in kinds:
            self.pos += 1
            return tok
        return None

    def expect(self, kind: str) -> Token:
        tok = self.peek()
        if tok.kind != kind:
            raise GscSyntaxError(
                f"{self.filename}:{tok.line}: expected {kind!r}, got {tok.kind!r} ({tok.value!r})"
            )
        self.pos += 1
        return tok

    def parse_module(self) -> dict[str, FunctionDef]:
        functions: dict[str, FunctionDef] = {}
        while self.peek().kind != "EOF":
            fn = self.parse_function()
            key = fn.name.lower()
            if key in functions:
                raise GscSyntaxError(f"{self.filename}:{fn.line}: duplicate function {fn.name!r}")
            functions[key] = fn
        return functions

    def parse_function(self) -> FunctionDef:
        name_tok = self.expect("IDENT")
        self.expect("(")
        params: list[str] = []
        if self.peek().kind != ")":
            params.append(self.expect("IDENT").value)
            while self.match(","):
                params.append(self.expect("IDENT").value)
        self.expect(")")
        body = self.parse_block()
        return FunctionDef(name=name_tok.value, params=params, body=body, line=name_tok.line)

    def parse_block(self) -> BlockStmt:
        self.expect("{")
        stmts: list[Any] = []
        while self.peek().kind != "}":
            if self.peek().kind == "EOF":
                raise GscSyntaxError(f"{self.filename}: unexpected EOF inside block")
            stmts.append(self.parse_stmt())
        self.expect("}")
        return BlockStmt(stmts)

    def parse_stmt(self) -> Any:
        tok = self.peek()
        if tok.kind == "{":
            return self.parse_block()
        if tok.kind == "IF":
            return self.parse_if()
        if tok.kind == "FOR":
            return self.parse_for()
        if tok.kind == "WHILE":
            return self.parse_while()
        if tok.kind == "RETURN":
            self.pos += 1
            if self.match(";"):
                return ReturnStmt(None)
            val = self.parse_expr()
            self.expect(";")
            return ReturnStmt(val)
        if tok.kind == "BREAK":
            self.pos += 1
            self.expect(";")
            return BreakStmt()
        if tok.kind == "CONTINUE":
            self.pos += 1
            self.expect(";")
            return ContinueStmt()
        if tok.kind == ";":
            self.pos += 1
            return BlockStmt([])
        expr = self.parse_expr()
        self.expect(";")
        return ExprStmt(expr)

    def parse_if(self) -> IfStmt:
        self.expect("IF")
        self.expect("(")
        cond = self.parse_expr()
        self.expect(")")
        then_branch = self.parse_stmt()
        else_branch = None
        if self.match("ELSE"):
            else_branch = self.parse_stmt()
        return IfStmt(cond=cond, then_branch=then_branch, else_branch=else_branch)

    def parse_for(self) -> ForStmt:
        self.expect("FOR")
        self.expect("(")
        init = None if self.peek().kind == ";" else self.parse_expr()
        self.expect(";")
        cond = None if self.peek().kind == ";" else self.parse_expr()
        self.expect(";")
        step = None if self.peek().kind == ")" else self.parse_expr()
        self.expect(")")
        body = self.parse_stmt()
        return ForStmt(init=init, cond=cond, step=step, body=body)

    def parse_while(self) -> WhileStmt:
        self.expect("WHILE")
        self.expect("(")
        cond = self.parse_expr()
        self.expect(")")
        body = self.parse_stmt()
        return WhileStmt(cond=cond, body=body)

    def parse_expr(self) -> Any:
        return self.parse_assignment()

    def parse_assignment(self) -> Any:
        left = self.parse_or()
        op_tok = self.match("=", "+=", "-=", "*=", "/=")
        if op_tok is not None:
            right = self.parse_assignment()
            return AssignExpr(target=left, op=op_tok.kind, value=right)
        return left

    def parse_or(self) -> Any:
        expr = self.parse_and()
        while self.match("||"):
            right = self.parse_and()
            expr = BinaryExpr("||", expr, right)
        return expr

    def parse_and(self) -> Any:
        expr = self.parse_equality()
        while self.match("&&"):
            right = self.parse_equality()
            expr = BinaryExpr("&&", expr, right)
        return expr

    def parse_equality(self) -> Any:
        expr = self.parse_relational()
        while True:
            op = self.match("==", "!=")
            if op is None:
                break
            expr = BinaryExpr(op.kind, expr, self.parse_relational())
        return expr

    def parse_relational(self) -> Any:
        expr = self.parse_additive()
        while True:
            op = self.match("<", "<=", ">", ">=")
            if op is None:
                break
            expr = BinaryExpr(op.kind, expr, self.parse_additive())
        return expr

    def parse_additive(self) -> Any:
        expr = self.parse_multiplicative()
        while True:
            op = self.match("+", "-")
            if op is None:
                break
            expr = BinaryExpr(op.kind, expr, self.parse_multiplicative())
        return expr

    def parse_multiplicative(self) -> Any:
        expr = self.parse_unary()
        while True:
            op = self.match("*", "/", "%")
            if op is None:
                break
            expr = BinaryExpr(op.kind, expr, self.parse_unary())
        return expr

    def parse_unary(self) -> Any:
        op = self.match("!", "-", "+")
        if op is not None:
            return UnaryExpr(op.kind, self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self) -> Any:
        expr = self.parse_primary()
        while True:
            if self.match("."):
                field = self.expect("IDENT").value
                expr = FieldAccess(expr, field)
            elif self.match("["):
                idx = self.parse_expr()
                self.expect("]")
                expr = IndexAccess(expr, idx)
            elif self.peek().kind in ("++", "--"):
                op = self.match("++", "--")
                assert op is not None
                expr = PostfixUpdateExpr(expr, op.kind)
            else:
                break
        return expr

    def parse_primary(self) -> Any:
        tok = self.peek()
        if tok.kind == "NUMBER":
            self.pos += 1
            return Literal(tok.value)
        if tok.kind == "STRING":
            self.pos += 1
            return Literal(tok.value)
        if tok.kind == "TRUE":
            self.pos += 1
            return Literal(True)
        if tok.kind == "FALSE":
            self.pos += 1
            return Literal(False)
        if tok.kind == "UNDEFINED":
            self.pos += 1
            return Literal(UNDEFINED)
        if tok.kind == "[":
            self.pos += 1
            self.expect("]")
            return ArrayLiteral()
        if tok.kind == "(":
            self.pos += 1
            expr = self.parse_expr()
            self.expect(")")
            return expr
        if tok.kind == "::":
            self.pos += 1
            fn_tok = self.expect("IDENT")
            return Literal(f"::{fn_tok.value}")
        if tok.kind == "IDENT":
            self.pos += 1
            if self.match("::"):
                fn_tok = self.expect("IDENT")
                args = self.parse_arg_list()
                return CallExpr(module_path=tok.value, func_name=fn_tok.value, args=args, line=fn_tok.line)
            if self.peek().kind == "(":
                args = self.parse_arg_list()
                return CallExpr(module_path=None, func_name=tok.value, args=args, line=tok.line)
            return VarRef(tok.value)

        raise GscSyntaxError(
            f"{self.filename}:{tok.line}: unexpected token {tok.kind!r} ({tok.value!r})"
        )

    def parse_arg_list(self) -> list[Any]:
        self.expect("(")
        args: list[Any] = []
        if self.peek().kind != ")":
            args.append(self.parse_expr())
            while self.match(","):
                args.append(self.parse_expr())
        self.expect(")")
        return args


# ---------------------------------------------------------------------------
# Evaluator & Fake Dvar Store
# ---------------------------------------------------------------------------

class _ReturnSignal(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


_ATOI_RE = re.compile(r"^\s*([+-]?\d+)")


def _waw_int(value: Any) -> int:
    if value is UNDEFINED or value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)  # C-style truncation toward zero
    if isinstance(value, str):
        m = _ATOI_RE.match(value)
        return int(m.group(1)) if m else 0
    raise GscRuntimeError(f"Cannot convert {value!r} to int")


def _waw_to_str(value: Any) -> str:
    if value is UNDEFINED:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value)


def _waw_truthy(value: Any) -> bool:
    if value is UNDEFINED or value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return len(value) > 0
    return True


class FakeDvarStore:
    """In-memory WaW server dvar store with case-insensitive keys and string values."""

    def __init__(self) -> None:
        self._dvars: dict[str, str] = {}

    def get(self, name: str) -> str:
        return self._dvars.get(name.lower(), "")

    def get_int(self, name: str) -> int:
        return _waw_int(self.get(name))

    def set(self, name: str, value: Any) -> None:
        self._dvars[name.lower()] = _waw_to_str(value)

    def snapshot(self) -> dict[str, str]:
        return dict(self._dvars)

    def clear(self) -> None:
        self._dvars.clear()


class GscRuntime:
    """Loads and executes WaW 1.7 `.gsc` modules rooted under `mod_root`."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        self.mod_root = Path(mod_root)
        self.dvars = dvars if dvars is not None else FakeDvarStore()
        self._modules: dict[str, dict[str, FunctionDef]] = {}

    def normalize_module_key(self, module_path: str) -> str:
        key = module_path.replace("\\", "/").lower()
        if key.endswith(".gsc"):
            key = key[:-4]
        return key

    def load_module(self, module_path: str) -> dict[str, FunctionDef]:
        key = self.normalize_module_key(module_path)
        if key not in self._modules:
            gsc_file = self.mod_root / f"{key}.gsc"
            if not gsc_file.is_file():
                raise FileNotFoundError(f"GSC module not found: {gsc_file}")
            source = gsc_file.read_text(encoding="latin1")
            tokens = tokenize(source, filename=str(gsc_file))
            self._modules[key] = Parser(tokens, filename=str(gsc_file)).parse_module()
        return self._modules[key]

    def call(self, module_path: str, func_name: str, *args: Any) -> Any:
        mod_key = self.normalize_module_key(module_path)
        module = self.load_module(mod_key)
        fn = module.get(func_name.lower())
        if fn is None:
            raise GscRuntimeError(f"Function {func_name!r} not found in module {mod_key!r}")
        env: dict[str, Any] = {}
        for idx, param in enumerate(fn.params):
            env[param.lower()] = args[idx] if idx < len(args) else UNDEFINED
        try:
            self._exec_block(fn.body, mod_key, env)
        except _ReturnSignal as sig:
            return sig.value
        return UNDEFINED

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "isdefined":
            val = args[0] if args else UNDEFINED
            return True, (val is not UNDEFINED)
        if name_lower == "int":
            val = args[0] if args else UNDEFINED
            return True, _waw_int(val)
        if name_lower == "tolower":
            val = args[0] if args else ""
            if val is UNDEFINED:
                return True, ""
            return True, _waw_to_str(val).lower()
        if name_lower == "strtok":
            if len(args) < 2 or args[0] is UNDEFINED or args[1] is UNDEFINED:
                return True, GscArray([])
            text = _waw_to_str(args[0])
            delim_set = set(_waw_to_str(args[1]))
            parts: list[str] = []
            buf: list[str] = []
            for ch in text:
                if ch in delim_set:
                    if buf:
                        parts.append("".join(buf))
                        buf.clear()
                else:
                    buf.append(ch)
            if buf:
                parts.append("".join(buf))
            return True, GscArray(parts)
        if name_lower == "spawnstruct":
            return True, GscStruct()
        if name_lower == "getdvar":
            key = _waw_to_str(args[0]) if args else ""
            return True, self.dvars.get(key)
        if name_lower == "getdvarint":
            key = _waw_to_str(args[0]) if args else ""
            return True, self.dvars.get_int(key)
        if name_lower == "setdvar":
            if len(args) < 2:
                raise GscRuntimeError(f"line {line}: SetDvar requires 2 arguments")
            self.dvars.set(_waw_to_str(args[0]), args[1])
            return True, UNDEFINED
        if name_lower == "println":
            return True, UNDEFINED
        return False, UNDEFINED

    def _exec_block(self, block: BlockStmt, mod_key: str, env: dict[str, Any]) -> None:
        for stmt in block.statements:
            self._exec_stmt(stmt, mod_key, env)

    def _exec_stmt(self, stmt: Any, mod_key: str, env: dict[str, Any]) -> None:
        if isinstance(stmt, BlockStmt):
            self._exec_block(stmt, mod_key, env)
        elif isinstance(stmt, IfStmt):
            if _waw_truthy(self._eval_expr(stmt.cond, mod_key, env)):
                self._exec_stmt(stmt.then_branch, mod_key, env)
            elif stmt.else_branch is not None:
                self._exec_stmt(stmt.else_branch, mod_key, env)
        elif isinstance(stmt, ForStmt):
            if stmt.init is not None:
                self._eval_expr(stmt.init, mod_key, env)
            while True:
                if stmt.cond is not None and not _waw_truthy(self._eval_expr(stmt.cond, mod_key, env)):
                    break
                try:
                    self._exec_stmt(stmt.body, mod_key, env)
                except _BreakSignal:
                    break
                except _ContinueSignal:
                    pass
                if stmt.step is not None:
                    self._eval_expr(stmt.step, mod_key, env)
        elif isinstance(stmt, WhileStmt):
            while _waw_truthy(self._eval_expr(stmt.cond, mod_key, env)):
                try:
                    self._exec_stmt(stmt.body, mod_key, env)
                except _BreakSignal:
                    break
                except _ContinueSignal:
                    continue
        elif isinstance(stmt, ReturnStmt):
            val = self._eval_expr(stmt.value, mod_key, env) if stmt.value is not None else UNDEFINED
            raise _ReturnSignal(val)
        elif isinstance(stmt, BreakStmt):
            raise _BreakSignal()
        elif isinstance(stmt, ContinueStmt):
            raise _ContinueSignal()
        elif isinstance(stmt, ExprStmt):
            self._eval_expr(stmt.expr, mod_key, env)
        else:
            raise GscRuntimeError(f"Unsupported statement node: {stmt!r}")

    def _read_target(self, target: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(target, VarRef):
            return env.get(target.name.lower(), UNDEFINED)
        if isinstance(target, FieldAccess):
            obj = self._eval_expr(target.obj, mod_key, env)
            if isinstance(obj, GscStruct):
                return obj.get_field(target.field)
            if isinstance(obj, GscArray) and target.field.lower() == "size":
                return obj.size
            if isinstance(obj, str) and target.field.lower() == "size":
                return len(obj)
            raise GscRuntimeError(f"Cannot read field {target.field!r} on {obj!r}")
        if isinstance(target, IndexAccess):
            obj = self._eval_expr(target.obj, mod_key, env)
            idx = self._eval_expr(target.index, mod_key, env)
            if isinstance(obj, GscArray):
                return obj.get_item(idx)
            if isinstance(obj, str):
                return obj[int(idx)]
            raise GscRuntimeError(f"Cannot index into {obj!r}")
        raise GscRuntimeError(f"Invalid read target: {target!r}")

    def _write_target(self, target: Any, value: Any, mod_key: str, env: dict[str, Any]) -> None:
        if isinstance(target, VarRef):
            env[target.name.lower()] = value
            return
        if isinstance(target, FieldAccess):
            obj = self._eval_expr(target.obj, mod_key, env)
            if not isinstance(obj, GscStruct):
                raise GscRuntimeError(f"Cannot set field {target.field!r} on {obj!r}")
            obj.set_field(target.field, value)
            return
        if isinstance(target, IndexAccess):
            obj = self._eval_expr(target.obj, mod_key, env)
            idx = self._eval_expr(target.index, mod_key, env)
            if not isinstance(obj, GscArray):
                raise GscRuntimeError(f"Cannot assign index on {obj!r}")
            obj.set_item(idx, value)
            return
        raise GscRuntimeError(f"Invalid assignment target: {target!r}")

    def _eval_expr(self, expr: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(expr, Literal):
            return expr.value
        if isinstance(expr, ArrayLiteral):
            return GscArray()
        if isinstance(expr, VarRef):
            return env.get(expr.name.lower(), UNDEFINED)
        if isinstance(expr, FieldAccess):
            return self._read_target(expr, mod_key, env)
        if isinstance(expr, IndexAccess):
            return self._read_target(expr, mod_key, env)
        if isinstance(expr, AssignExpr):
            rhs = self._eval_expr(expr.value, mod_key, env)
            if expr.op == "=":
                self._write_target(expr.target, rhs, mod_key, env)
                return rhs
            cur = self._read_target(expr.target, mod_key, env)
            base_op = expr.op[0]
            new_val = self._eval_binary_op(base_op, cur, rhs)
            self._write_target(expr.target, new_val, mod_key, env)
            return new_val
        if isinstance(expr, PostfixUpdateExpr):
            cur = self._read_target(expr.target, mod_key, env)
            delta = 1 if expr.op == "++" else -1
            self._write_target(expr.target, cur + delta, mod_key, env)
            return cur
        if isinstance(expr, UnaryExpr):
            val = self._eval_expr(expr.operand, mod_key, env)
            if expr.op == "!":
                return not _waw_truthy(val)
            if expr.op == "-":
                return -val
            if expr.op == "+":
                return +val
            raise GscRuntimeError(f"Unsupported unary operator: {expr.op}")
        if isinstance(expr, BinaryExpr):
            if expr.op == "&&":
                if not _waw_truthy(self._eval_expr(expr.left, mod_key, env)):
                    return False
                return _waw_truthy(self._eval_expr(expr.right, mod_key, env))
            if expr.op == "||":
                if _waw_truthy(self._eval_expr(expr.left, mod_key, env)):
                    return True
                return _waw_truthy(self._eval_expr(expr.right, mod_key, env))
            left = self._eval_expr(expr.left, mod_key, env)
            right = self._eval_expr(expr.right, mod_key, env)
            return self._eval_binary_op(expr.op, left, right)
        if isinstance(expr, CallExpr):
            eval_args = [self._eval_expr(a, mod_key, env) for a in expr.args]
            if expr.module_path is not None:
                return self.call(expr.module_path, expr.func_name, *eval_args)
            handled, res = self._call_builtin(expr.func_name.lower(), eval_args, expr.line)
            if handled:
                return res
            return self.call(mod_key, expr.func_name, *eval_args)
        raise GscRuntimeError(f"Unsupported expression node: {expr!r}")

    def _eval_binary_op(self, op: str, left: Any, right: Any) -> Any:
        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return _waw_to_str(left) + _waw_to_str(right)
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return left / right
        if op == "%":
            return left % right
        if op == "==":
            if left is UNDEFINED or right is UNDEFINED:
                return left is right
            return left == right
        if op == "!=":
            if left is UNDEFINED or right is UNDEFINED:
                return left is not right
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        raise GscRuntimeError(f"Unsupported binary operator: {op}")
