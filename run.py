#!/usr/bin/env python
from functools import wraps
from typing import io, Callable


def rollback(parser):
    """
    >>> from io import StringIO
    >>> @rollback
    ... def raise_error(stream):
    ...     stream.read(1)
    ...     raise SyntaxError('test')
    >>> a = StringIO("test")
    >>> position = a.tell()
    >>> raise_error(a)
    Traceback (most recent call last):
        ...
    SyntaxError: test
    >>> assert a.tell() == position
    """
    @wraps(parser)
    def wrapper(stream):
        start = stream.tell()
        try:
            return parser(stream)
        except SyntaxError as e:
            stream.seek(start)
            raise e
    return wrapper


def concatenation(*parsers, separator=None):
    """
    >>> from io import StringIO
    >>> a = concatenation(
    ... number(), whitespace(), number(), whitespace(), name())
    >>> a(StringIO("123 123 bravo"))
    [123, ' ', 123, ' ', 'bravo']
    """
    def parse(stream):
        return [parser(stream) for parser in parsers]
    return parse


def alternation(*parsers):
    """
    >>> from io import StringIO
    >>> a = alternation(number(), name())
    >>> a(StringIO("bravo"))
    'bravo'
    >>> a(StringIO("123"))
    123
    """
    def parse(stream):
        for parser in parsers:
            try:
                return parser(stream)
            except:
                continue
        raise SyntaxError("Exhausted all parsers")
    return parse


def zero_or_more(parser, separator=None):
    """
    >>> from io import StringIO
    >>> a = zero_or_more(keyword('bla'))
    >>> list(a(StringIO("blabla")))
    ['bla', 'bla']
    >>> list(a(StringIO("")))
    []
    """
    def parse(stream):
        def _result():
            while True:
                try:
                    yield parser(stream)
                except SyntaxError:
                    break
        return list(_result())
    return parse


def one_or_more(parser, separator=None):
    """
    >>> from io import StringIO
    >>> a = one_or_more(number())
    >>> list(a(StringIO("123")))
    [123]
    >>> list(a(StringIO("")))
    Traceback (most recent call last):
        ...
    SyntaxError: Expected one or more tokens
    """
    def parse(stream):
        count = 0
        while True:
            try:
                yield parser(stream)
                count += 1
            except (SyntaxError, EOFError):
                break
        if not count:
            raise SyntaxError("Expected one or more tokens")
    return parse


def maybe(parser):
    """
    >>> from io import StringIO
    >>> a = maybe(number())
    >>> a(StringIO("123"))
    123
    >>> a(StringIO(""))
    """
    def parse(stream):
        try:
            return parser(stream)
        except (SyntaxError, EOFError):
            return None
    return parse


def number():
    """
    >>> from io import StringIO
    >>> a = StringIO("1 123")
    >>> number()(a)
    1
    >>> a.tell()
    1
    """
    @rollback
    def parse(stream):
        def _result():
            yield match(stream, lambda a: a.isdigit())
            while True:
                try:
                    yield match(stream, lambda a: a.isdigit())
                except EOFError:
                    break
                except SyntaxError:
                    match(stream, lambda a: a.isspace(), rollback=True)
                    break
        try:
            return int("".join(_result()))
        except ValueError as e:
            raise SyntaxError(e)

    return parse


def name() -> Callable:
    """
    >>> from io import StringIO
    >>> a = StringIO("a ")
    >>> name()(a)
    'a'
    >>> a.tell()
    1
    >>> name()(StringIO("123k 123")) #doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    SyntaxError: Could not match ...
    """
    @rollback
    def parse(stream: io) -> str:
        def _result():
            yield match(stream, lambda a: a.isalpha())
            while True:
                try:
                    yield match(stream, lambda a: a.isalnum())
                except EOFError:
                    break
                except SyntaxError:
                    match(stream, lambda a: a.isspace(), rollback=True)
                    break
        return "".join(_result())
    return parse


def keyword(value: str) -> Callable[[io], str]:
    """
    >>> from io import StringIO
    >>> keyword("bla")(StringIO(""))
    Traceback (most recent call last):
        ...
    SyntaxError: Expected  to match bla
    >>> keyword("bla")(StringIO("bla 123"))
    'bla'
    """
    @rollback
    def parse(stream: io) -> str:
        content = stream.read(len(value))
        if value == content:
            return value
        raise SyntaxError("Expected {} to match {}".format(
            content, value))
    return parse


def whitespace(minimum_count=0):
    """
    >>> a = StringIO("  ")
    >>> whitespace(3)(a)
    Traceback (most recent call last):
        ...
    SyntaxError: Not enough whitespace to match.
    >>> a.tell()
    0
    >>> whitespace(2)(a)
    '  '
    >>> a.tell()
    2
    """
    @rollback
    def parse(stream: io) -> str:
        def _result():
            try:
                for _ in range(minimum_count):
                    yield match(stream, lambda a: a.isspace())
            except (SyntaxError, EOFError):
                raise SyntaxError("Not enough whitespace to match.")
            while True:
                try:
                    yield match(stream, lambda a: a.isspace())
                except (SyntaxError, EOFError):
                    break
        return "".join(_result())
    return parse


def match(stream, predicate, rollback=False):
    """
    >>> from io import StringIO
    >>> a = StringIO("a1")
    >>> match(a, lambda a: a.isalpha())
    'a'
    >>> match(a, lambda a: a.isalpha())
    Traceback (most recent call last):
        ...
    SyntaxError: Could not match '1' with the given predicate
    >>> match(a, lambda a: a.isdigit())
    '1'
    >>> match(a, lambda a: a.isdigit())
    Traceback (most recent call last):
        ...
    EOFError
    """
    position = stream.tell()
    character = stream.read(1)
    if predicate(character):
        if rollback:
            stream.seek(position)
        return character
    if character:
        stream.seek(position)
        raise SyntaxError(
            "Could not match {} with the given predicate".format(
                repr(character)))
    raise EOFError()


from io import StringIO
from sys import stdin

value = alternation(
    number(),
    lambda e: expression(e),
)
product = concatenation(
    value,
    zero_or_more(
        concatenation(
            alternation(keyword('*'), keyword('/')),
            value,
        )
    ),
)

sum = concatenation(
    value,
    whitespace(),
    zero_or_more(
        concatenation(
            alternation(keyword('+'), keyword('-')),
            whitespace(),
            value,
        )
    )
)

expression = sum


if __name__ == "__main__":
    stream = stdin
    if not stream.seekable():
        content = stream.read()
        stream = StringIO(content)
    print(list(expression(stream)))
