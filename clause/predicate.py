"""Predicate expression language for Rialo reactive transactions.

A reactive transaction on Rialo registers a predicate: a logical expression
that validators re-evaluate whenever one of its inputs changes. When the
expression turns true, the attached transaction is enqueued by the protocol
itself, with no keeper, bot or cron in the path.

This module gives Clause three things it needs everywhere else:

  parse()        turns predicate source into an abstract syntax tree
  dependencies() reports exactly which signals an expression reads
  evaluate()     deterministically resolves an expression against a snapshot

The dependency set is the important one. Rialo's block pipeline re-evaluates
only those predicates whose dependencies may have changed during the block, so
an explorer that wants to explain why something fired has to model the same
edge. Clause builds an inverted index from dependency key to armed predicate,
which is the same shape a validator maintains.

Grammar:

    expression  := disjunction
    disjunction := conjunction ( "or" conjunction )*
    conjunction := negation ( "and" negation )*
    negation    := "not" negation | comparison
    comparison  := sum ( ( "<" | "<=" | ">" | ">=" | "==" | "!=" ) sum )?
    sum         := product ( ( "+" | "-" ) product )*
    product     := unary ( ( "*" | "/" | "%" ) unary )*
    unary       := "-" unary | postfix
    postfix     := primary ( "." NAME | "(" arguments ")" )*
    primary     := NUMBER | STRING | "true" | "false" | NAME | "(" expression ")"

Signal sources are ordinary calls, which keeps the grammar small:

    oracle("AAPL").price              validator attested market data
    state("lending/pos_7f2a").health  onchain account state
    event("perps/Liquidation").count  events emitted by earlier transactions
    edge("api.example.com/x").status  validator attested web2 response
    workflow("5UfDuX").step           result of an earlier workflow step
    time.block, time.timestamp        block height and wall clock
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

__all__ = [
    "PredicateError",
    "ParseError",
    "EvaluationError",
    "Node",
    "Literal",
    "Signal",
    "TimeSignal",
    "Unary",
    "Binary",
    "Dependency",
    "parse",
    "dependencies",
    "evaluate",
    "describe",
]

# Sources that resolve to an external or onchain signal. Each takes a single
# string reference, and attribute access on the result names the field read.
SIGNAL_SOURCES = frozenset({"oracle", "state", "event", "edge", "workflow"})

# Human readable labels used when rendering a predicate in the interface.
SOURCE_LABELS = {
    "oracle": "oracle feed",
    "state": "onchain state",
    "event": "emitted event",
    "edge": "web2 endpoint",
    "workflow": "workflow step",
    "time": "clock",
}


class PredicateError(Exception):
    """Base class for every failure raised by this module."""


class ParseError(PredicateError):
    """Raised when predicate source cannot be turned into a tree."""

    def __init__(self, message: str, position: int, source: str) -> None:
        self.position = position
        self.source = source
        caret = " " * position + "^"
        super().__init__(f"{message} at column {position + 1}\n  {source}\n  {caret}")


class EvaluationError(PredicateError):
    """Raised when a well formed expression cannot be resolved."""


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------


class Node:
    """Base class for every node in a predicate tree."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Literal(Node):
    """A constant number, string or boolean."""

    value: Any

    def __str__(self) -> str:
        if isinstance(self.value, str):
            return f'"{self.value}"'
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if isinstance(self.value, float) and self.value.is_integer():
            return str(int(self.value))
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Signal(Node):
    """A read from an external or onchain source.

    ``source`` is one of SIGNAL_SOURCES, ``reference`` identifies the feed,
    account or endpoint, and ``field`` is the property being read.
    """

    source: str
    reference: str
    field: str

    def __str__(self) -> str:
        return f'{self.source}("{self.reference}").{self.field}'

    @property
    def key(self) -> str:
        """The dependency key a validator would index this read under."""
        return f"{self.source}:{self.reference}"


@dataclass(frozen=True, slots=True)
class TimeSignal(Node):
    """A read from the chain clock: ``time.block`` or ``time.timestamp``."""

    field: str

    def __str__(self) -> str:
        return f"time.{self.field}"

    @property
    def key(self) -> str:
        return f"time:{self.field}"


@dataclass(frozen=True, slots=True)
class Unary(Node):
    """Negation, either logical or arithmetic."""

    operator: str
    operand: Node

    def __str__(self) -> str:
        if self.operator == "not":
            return f"not {self.operand}"
        return f"-{self.operand}"


@dataclass(frozen=True, slots=True)
class Binary(Node):
    """Any infix operation."""

    operator: str
    left: Node
    right: Node

    def __str__(self) -> str:
        return f"({self.left} {self.operator} {self.right})"


@dataclass(frozen=True, slots=True)
class Dependency:
    """One signal a predicate reads, flattened for indexing."""

    key: str
    source: str
    reference: str
    field: str

    @property
    def label(self) -> str:
        if self.source == "time":
            return "block height" if self.field == "block" else "chain timestamp"
        source = SOURCE_LABELS.get(self.source, self.source)
        return f"{source} {self.reference}.{self.field}"


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TOKEN_SPEC: Sequence[tuple[str, str]] = (
    ("WHITESPACE", r"[ \t\r\n]+"),
    ("NUMBER", r"\d[\d_]*\.\d+|\d[\d_]*"),
    ("STRING", r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''),
    ("NAME", r"[A-Za-z_][A-Za-z_0-9]*"),
    ("OPERATOR", r"<=|>=|==|!=|&&|\|\||[<>+\-*/%.(),]"),
)

_TOKEN_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC)
)

# Words that behave as operators rather than identifiers.
_KEYWORD_OPERATORS = {"and", "or", "not"}
_KEYWORD_LITERALS = {"true": True, "false": False}


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: Any
    position: int


def _tokenize(source: str) -> list[_Token]:
    """Split predicate source into tokens, rejecting anything unrecognised."""
    tokens: list[_Token] = []
    index = 0
    length = len(source)

    while index < length:
        match = _TOKEN_RE.match(source, index)
        if match is None:
            raise ParseError(f"unexpected character {source[index]!r}", index, source)

        kind = match.lastgroup
        text = match.group()
        position = index
        index = match.end()

        if kind == "WHITESPACE":
            continue

        if kind == "NUMBER":
            cleaned = text.replace("_", "")
            value: Any = float(cleaned) if "." in cleaned else int(cleaned)
            tokens.append(_Token("NUMBER", value, position))
            continue

        if kind == "STRING":
            tokens.append(_Token("STRING", _unquote(text), position))
            continue

        if kind == "NAME":
            lowered = text.lower()
            if lowered in _KEYWORD_OPERATORS:
                tokens.append(_Token("OPERATOR", lowered, position))
            elif lowered in _KEYWORD_LITERALS:
                tokens.append(_Token("BOOLEAN", _KEYWORD_LITERALS[lowered], position))
            else:
                tokens.append(_Token("NAME", text, position))
            continue

        # Accept the symbolic forms of the logical operators as aliases so
        # predicates copied out of Rust or TypeScript sources still parse.
        if text == "&&":
            tokens.append(_Token("OPERATOR", "and", position))
        elif text == "||":
            tokens.append(_Token("OPERATOR", "or", position))
        else:
            tokens.append(_Token("OPERATOR", text, position))

    tokens.append(_Token("END", None, length))
    return tokens


def _unquote(text: str) -> str:
    """Strip surrounding quotes and resolve the escapes the lexer allows."""
    body = text[1:-1]
    return (
        body.replace("\\\\", "\x00")
        .replace('\\"', '"')
        .replace("\\'", "'")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\x00", "\\")
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_COMPARISONS = frozenset({"<", "<=", ">", ">=", "==", "!="})


class _Parser:
    """Recursive descent parser over the token stream."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = _tokenize(source)
        self.cursor = 0

    # -- token helpers ----------------------------------------------------

    @property
    def current(self) -> _Token:
        return self.tokens[self.cursor]

    def advance(self) -> _Token:
        token = self.tokens[self.cursor]
        self.cursor += 1
        return token

    def at_operator(self, *operators: str) -> bool:
        token = self.current
        return token.kind == "OPERATOR" and token.value in operators

    def expect_operator(self, operator: str) -> _Token:
        if not self.at_operator(operator):
            raise ParseError(
                f"expected {operator!r} but found {self._describe(self.current)}",
                self.current.position,
                self.source,
            )
        return self.advance()

    @staticmethod
    def _describe(token: _Token) -> str:
        if token.kind == "END":
            return "end of expression"
        return repr(token.value)

    # -- grammar ----------------------------------------------------------

    def parse(self) -> Node:
        if self.current.kind == "END":
            raise ParseError("empty predicate", 0, self.source)
        node = self.parse_disjunction()
        if self.current.kind != "END":
            raise ParseError(
                f"unexpected {self._describe(self.current)}",
                self.current.position,
                self.source,
            )
        return node

    def parse_disjunction(self) -> Node:
        node = self.parse_conjunction()
        while self.at_operator("or"):
            self.advance()
            node = Binary("or", node, self.parse_conjunction())
        return node

    def parse_conjunction(self) -> Node:
        node = self.parse_negation()
        while self.at_operator("and"):
            self.advance()
            node = Binary("and", node, self.parse_negation())
        return node

    def parse_negation(self) -> Node:
        if self.at_operator("not"):
            self.advance()
            return Unary("not", self.parse_negation())
        return self.parse_comparison()

    def parse_comparison(self) -> Node:
        node = self.parse_sum()
        if self.current.kind == "OPERATOR" and self.current.value in _COMPARISONS:
            operator = self.advance().value
            node = Binary(operator, node, self.parse_sum())
        return node

    def parse_sum(self) -> Node:
        node = self.parse_product()
        while self.at_operator("+", "-"):
            operator = self.advance().value
            node = Binary(operator, node, self.parse_product())
        return node

    def parse_product(self) -> Node:
        node = self.parse_unary()
        while self.at_operator("*", "/", "%"):
            operator = self.advance().value
            node = Binary(operator, node, self.parse_unary())
        return node

    def parse_unary(self) -> Node:
        if self.at_operator("-"):
            self.advance()
            return Unary("-", self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self) -> Node:
        token = self.current

        if token.kind == "NAME":
            name = token.value
            if name in SIGNAL_SOURCES:
                return self.parse_signal(name)
            if name == "time":
                return self.parse_time()
            raise ParseError(
                f"unknown source {name!r}; expected one of "
                f"{', '.join(sorted(SIGNAL_SOURCES | {'time'}))}",
                token.position,
                self.source,
            )

        return self.parse_primary()

    def parse_signal(self, source: str) -> Node:
        start = self.advance().position
        self.expect_operator("(")

        argument = self.current
        if argument.kind != "STRING":
            raise ParseError(
                f"{source}() takes a quoted reference",
                argument.position,
                self.source,
            )
        reference = self.advance().value
        if not reference.strip():
            raise ParseError(
                f"{source}() reference cannot be empty", argument.position, self.source
            )

        self.expect_operator(")")
        self.expect_operator(".")

        field_token = self.current
        if field_token.kind != "NAME":
            raise ParseError(
                f"expected a field name after {source}(...)",
                field_token.position,
                self.source,
            )
        field = self.advance().value

        # Guard against a trailing chain such as oracle("X").a.b, which has no
        # meaning here and is almost always a typo.
        if self.at_operator("."):
            raise ParseError(
                "signal fields are not nested", self.current.position, self.source
            )

        del start
        return Signal(source, reference, field)

    def parse_time(self) -> Node:
        self.advance()
        self.expect_operator(".")
        field_token = self.current
        if field_token.kind != "NAME":
            raise ParseError(
                "expected time.block or time.timestamp",
                field_token.position,
                self.source,
            )
        field = self.advance().value
        if field not in {"block", "timestamp"}:
            raise ParseError(
                f"unknown clock field {field!r}; use block or timestamp",
                field_token.position,
                self.source,
            )
        return TimeSignal(field)

    def parse_primary(self) -> Node:
        token = self.current

        if token.kind in {"NUMBER", "STRING", "BOOLEAN"}:
            self.advance()
            return Literal(token.value)

        if self.at_operator("("):
            self.advance()
            node = self.parse_disjunction()
            self.expect_operator(")")
            return node

        raise ParseError(
            f"unexpected {self._describe(token)}", token.position, self.source
        )


def parse(source: str) -> Node:
    """Parse predicate source into a tree.

    >>> str(parse('oracle("AAPL").price < 210'))
    '(oracle("AAPL").price < 210)'
    """
    if not isinstance(source, str):
        raise ParseError("predicate must be a string", 0, str(source))
    return _Parser(source).parse()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def dependencies(node: Node | str) -> list[Dependency]:
    """List every signal an expression reads, in stable sorted order.

    This is what Clause indexes on. When a block changes ``oracle:AAPL``, every
    armed predicate carrying that key is a candidate for re-evaluation, which
    is the same narrowing a validator performs before running predicates.
    """
    tree = parse(node) if isinstance(node, str) else node
    found: dict[str, Dependency] = {}

    def walk(current: Node) -> None:
        if isinstance(current, Signal):
            dependency = Dependency(
                key=current.key,
                source=current.source,
                reference=current.reference,
                field=current.field,
            )
            found.setdefault(f"{dependency.key}.{dependency.field}", dependency)
        elif isinstance(current, TimeSignal):
            dependency = Dependency(
                key=current.key,
                source="time",
                reference="chain",
                field=current.field,
            )
            found.setdefault(f"{dependency.key}", dependency)
        elif isinstance(current, Unary):
            walk(current.operand)
        elif isinstance(current, Binary):
            walk(current.left)
            walk(current.right)

    walk(tree)
    return sorted(found.values(), key=lambda item: (item.key, item.field))


def dependency_keys(node: Node | str) -> set[str]:
    """The bare set of dependency keys, for inverted index lookups."""
    return {dependency.key for dependency in dependencies(node)}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

# Snapshot shape: {"oracle": {"AAPL": {"price": 210.4}}, "time": {"block": 12}}
Snapshot = dict[str, dict[str, Any]]


def evaluate(node: Node | str, snapshot: Snapshot) -> Any:
    """Resolve an expression against a snapshot of chain and feed state.

    Evaluation is deterministic and total: a missing signal raises rather than
    defaulting, because a validator that silently read zero would fire
    liquidations that nobody asked for.
    """
    tree = parse(node) if isinstance(node, str) else node
    return _evaluate(tree, snapshot)


def _evaluate(node: Node, snapshot: Snapshot) -> Any:
    if isinstance(node, Literal):
        return node.value

    if isinstance(node, TimeSignal):
        clock = snapshot.get("time")
        if not isinstance(clock, dict) or node.field not in clock:
            raise EvaluationError(f"snapshot is missing time.{node.field}")
        return clock[node.field]

    if isinstance(node, Signal):
        bucket = snapshot.get(node.source)
        if not isinstance(bucket, dict):
            raise EvaluationError(f"snapshot is missing source {node.source!r}")
        entry = bucket.get(node.reference)
        if entry is None:
            raise EvaluationError(
                f"snapshot is missing {node.source}({node.reference!r})"
            )
        if isinstance(entry, dict):
            if node.field not in entry:
                raise EvaluationError(f"{node} is not present in the snapshot")
            return entry[node.field]
        raise EvaluationError(f"{node.source}({node.reference!r}) is not a record")

    if isinstance(node, Unary):
        if node.operator == "not":
            return not _truthy(_evaluate(node.operand, snapshot))
        value = _evaluate(node.operand, snapshot)
        _require_number(value, node)
        return -value

    if isinstance(node, Binary):
        return _evaluate_binary(node, snapshot)

    raise EvaluationError(f"unsupported node {type(node).__name__}")


def _evaluate_binary(node: Binary, snapshot: Snapshot) -> Any:
    operator = node.operator

    # Short circuit so that a predicate guarded by a cheap test never demands
    # a signal the snapshot does not carry.
    if operator == "and":
        if not _truthy(_evaluate(node.left, snapshot)):
            return False
        return _truthy(_evaluate(node.right, snapshot))
    if operator == "or":
        if _truthy(_evaluate(node.left, snapshot)):
            return True
        return _truthy(_evaluate(node.right, snapshot))

    left = _evaluate(node.left, snapshot)
    right = _evaluate(node.right, snapshot)

    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right

    if operator in {"<", "<=", ">", ">="}:
        if isinstance(left, str) != isinstance(right, str):
            raise EvaluationError(
                f"cannot order {left!r} against {right!r} in {node}"
            )
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
        if operator == ">":
            return left > right
        return left >= right

    _require_number(left, node)
    _require_number(right, node)

    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    if operator == "*":
        return left * right
    if operator == "/":
        if right == 0:
            raise EvaluationError(f"division by zero in {node}")
        return left / right
    if operator == "%":
        if right == 0:
            raise EvaluationError(f"modulo by zero in {node}")
        return left % right

    raise EvaluationError(f"unsupported operator {operator!r}")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return bool(value)
    raise EvaluationError(f"{value!r} is not a boolean")


def _require_number(value: Any, node: Node) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationError(f"{value!r} is not a number in {node}")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_PLAIN_OPERATORS = {
    "<": "goes below",
    "<=": "is at or below",
    ">": "goes above",
    ">=": "reaches",
    "==": "equals",
    "!=": "stops being",
    "and": "and",
    "or": "or",
}


def describe(node: Node | str) -> str:
    """Render a predicate as a sentence, for people reading the interface.

    The parsed form is the source of truth; this is presentation only.
    """
    tree = parse(node) if isinstance(node, str) else node
    return _describe(tree)


def _describe(node: Node) -> str:
    if isinstance(node, Literal):
        return str(node)

    if isinstance(node, TimeSignal):
        return "block height" if node.field == "block" else "chain clock"

    if isinstance(node, Signal):
        label = SOURCE_LABELS.get(node.source, node.source)
        readable = node.field.replace("_", " ")
        return f"{readable} on {label} {node.reference}"

    if isinstance(node, Unary):
        if node.operator == "not":
            return f"it is not the case that {_describe(node.operand)}"
        return f"minus {_describe(node.operand)}"

    if isinstance(node, Binary):
        left = _describe(node.left)
        right = _describe(node.right)
        if node.operator in {"and", "or"}:
            return f"{left} {node.operator} {right}"
        phrase = _PLAIN_OPERATORS.get(node.operator)
        if phrase:
            return f"{left} {phrase} {right}"
        return f"{left} {node.operator} {right}"

    return str(node)


def signals_of(node: Node | str) -> Iterable[Signal | TimeSignal]:
    """Yield each signal node in the tree, left to right."""
    tree = parse(node) if isinstance(node, str) else node

    def walk(current: Node):
        if isinstance(current, (Signal, TimeSignal)):
            yield current
        elif isinstance(current, Unary):
            yield from walk(current.operand)
        elif isinstance(current, Binary):
            yield from walk(current.left)
            yield from walk(current.right)

    return list(walk(tree))
