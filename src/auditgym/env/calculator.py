"""Decimal calculator: numbers, + - * / ( ) and unary minus. Nothing else (brief §04)."""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, DivisionByZero, InvalidOperation, localcontext

MAX_LEN, MAX_DIGITS, MAX_DEPTH, MAX_RESULT_DIGITS = 200, 30, 20, 60


class CalcError(ValueError):
    pass


class _Parser:
    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0
        self.depth = 0

    def peek(self) -> str:
        while self.i < len(self.s) and self.s[self.i] == " ":
            self.i += 1
        return self.s[self.i] if self.i < len(self.s) else ""

    def expr(self) -> Decimal:
        v = self.term()
        while self.peek() in ("+", "-"):
            op = self.s[self.i]
            self.i += 1
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def term(self) -> Decimal:
        v = self.unary()
        while self.peek() in ("*", "/"):
            op = self.s[self.i]
            self.i += 1
            r = self.unary()
            if op == "*":
                v = v * r
            else:
                if r == 0:
                    raise CalcError("division by zero")
                v = v / r
        return v

    def unary(self) -> Decimal:
        if self.peek() == "-":
            self.i += 1
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise CalcError("expression too deep")
            v = -self.unary()
            self.depth -= 1
            return v
        if self.peek() == "+":
            raise CalcError("unexpected '+'")
        return self.atom()

    def atom(self) -> Decimal:
        c = self.peek()
        if c == "(":
            self.i += 1
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise CalcError("expression too deep")
            v = self.expr()
            if self.peek() != ")":
                raise CalcError("missing ')'")
            self.i += 1
            self.depth -= 1
            return v
        start = self.i
        seen_dot = False
        while self.i < len(self.s) and (self.s[self.i] in "0123456789" or (self.s[self.i] == "." and not seen_dot)):
            seen_dot = seen_dot or self.s[self.i] == "."
            self.i += 1
        tok = self.s[start:self.i]
        if not tok or tok == ".":
            raise CalcError("expected a number")
        if sum(ch.isdigit() for ch in tok) > MAX_DIGITS:
            raise CalcError("number too long")
        return Decimal(tok)


def evaluate(expression: object) -> str:
    if not isinstance(expression, str):
        raise CalcError("expression must be a string")
    if len(expression) > MAX_LEN:
        raise CalcError("expression too long")
    if any(ch not in "0123456789.+-*/() " for ch in expression):
        raise CalcError("only digits, '.', + - * / ( ) and spaces are allowed")
    with localcontext() as ctx:
        ctx.prec = 34
        ctx.rounding = ROUND_HALF_EVEN
        ctx.traps[DivisionByZero] = True
        ctx.traps[InvalidOperation] = True
        p = _Parser(expression)
        try:
            v = p.expr()
        except (InvalidOperation, DivisionByZero) as exc:
            raise CalcError("invalid arithmetic") from exc
        if p.peek() != "":
            raise CalcError("unexpected character")
        if abs(v.adjusted()) > MAX_RESULT_DIGITS:
            raise CalcError("result too large")
        return format(v, "f")
