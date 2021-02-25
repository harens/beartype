#!/usr/bin/env python3
# --------------------( LICENSE                           )--------------------
# Copyright (c) 2014-2021 Cecil Curry.
# See "LICENSE" for further details.

'''
**Type hint cache** (i.e., singleton dictionary mapping from the
machine-readable representations of all non-self-cached type hints to those
hints).**

This private submodule is *not* intended for importation by downstream callers.
'''

# ....................{ TODO                              }....................
#FIXME: The coercion function(s) defined below should also rewrite unhashable
#hints to be hashable *IF FEASIBLE.* This isn't always feasible, of course
#(e.g., "Annotated[[]]", "Literal[[]]"). The one notable place where this is
#feasible is with PEP 585-compliant type hints subscripted by unhashable rather
#than hashable iterables, which can *ALWAYS* be safely rewritten to be hashable
#(e.g., coercing "callable[[], None]" to "callable[(), None]").

# ....................{ IMPORTS                           }....................
from beartype._util.hint.utilhinttest import die_unless_hint
from collections.abc import Callable
from typing import Any, Dict, Union

# See the "beartype.cave" submodule for further commentary.
__all__ = ['STAR_IMPORTS_CONSIDERED_HARMFUL']

# ....................{ GLOBALS                           }....................
_HINT_REPR_TO_HINT: Dict[str, Any] = {}
'''
**Type hint cache** (i.e., singleton dictionary mapping from the
machine-readable representations of all non-self-cached type hints to those
hints).**

This dictionary caches:

* `PEP 585`_-compliant type hints, which do *not* cache themselves.
* `PEP 563`_-compliant **deferred type hints** (i.e., type hints persisted as
  evaluatable strings rather than actual type hints), enabled if the active
  Python interpreter targets either:

  * Python 3.7.0 *and* the module declaring this callable explicitly enables
    `PEP 563`_ support with a leading dunder importation of the form ``from
    __future__ import annotations``.
  * Python 4.0.0, where `PEP 563`_ is expected to be mandatory.

This dictionary does *not* cache:

* Type hints declared by the :mod:`typing` module, which implicitly cache
  themselves on subscription thanks to inscrutable metaclass magic.

Implementation
--------------
This dictionary is intentionally designed as a naive dictionary rather than
robust LRU cache, for the same reasons that callables accepting hints are
memoized by the :func:`beartype._util.cache.utilcachecall.callable_cached`
rather than the :func:`functools.lru_cache` decorator. Why? Because:

* The number of different type hints instantiated across even worst-case
  codebases is negligible in comparison to the space consumed by those hints.
* The :attr:`sys.modules` dictionary persists strong references to all
  callables declared by previously imported modules. In turn, the
  ``func.__annotations__`` dunder dictionary of each such callable persists
  strong references to all type hints annotating that callable. In turn, these
  two statements imply that type hints are *never* garbage collected but
  instead persisted for the lifetime of the active Python process. Ergo,
  temporarily caching hints in an LRU cache is pointless, as there are *no*
  space savings in dropping stale references to unused hints.

.. _PEP 484:
    https://www.python.org/dev/peps/pep-0484
.. _PEP 563:
    https://www.python.org/dev/peps/pep-0563
.. _PEP 585:
    https://www.python.org/dev/peps/pep-0585
'''

# ....................{ CACHERS                           }....................
#FIXME: Replace all calls to coerce_hint_pep() with calls to this function.
def cache_hint_nonpep563(
    func: Callable,
    pith_name: str,
    hint: Any,
    hint_label: str,
) -> Any:
    '''
    Coerce and cache the passed (possibly non-self-cached and/or
    PEP-noncompliant) type hint annotating the parameter or return value with
    the passed name of the passed callable into the equivalent
    :mod:`beartype`-cached PEP-compliant type hint if needed *or* silently
    reduce to a noop otherwise (i.e., if this hint is already both self-cached
    and PEP-compliant).

    Specifically, this function (in order):

    #. If the passed type hint is already self-cached, this hint is already
       PEP-compliant by definition. In this case, this function preserves and
       returns this hint as is.
    #. Else if a semantically equivalent type hint (i.e., having the same
       machine-readable representation) as this hint was already cached by a
       prior call to this function, the current call to this function:

       * Replaces this hint in the ``__annotations__`` dunder tuple of this
         callable with this previously cached hint, minimizing memory space
         consumption across the lifetime of the active Python process.
       * Returns this previously cached hint.

    #. Else if this hint is a **PEP-noncompliant tuple union** (i.e., tuple of
       one or more standard classes and forward references to standard
       classes), this function:

       * Coerces this tuple union into the equivalent `PEP 484`_-compliant
         union.
       * Replaces this tuple union in the ``__annotations__`` dunder tuple of
         this callable with this `PEP 484`_-compliant union.

    #. Else (i.e., if this hint is neither PEP-compliant nor -noncompliant and
       thus unsupported by :mod:`beartype`), this function raises an exception.
    #. Internally caches this hint with the :data:`_HINT_REPR_TO_HINT`
       dictionary.
    #. Returns this hint.

    This function *cannot* be meaningfully memoized, since the passed type hint
    is *not* guaranteed to be cached somewhere. Only functions passed cached
    type hints can be meaningfully memoized.

    The ``_nonpep563`` substring suffixing the name of this function implies
    this function is intended to be called *after* all possibly `PEP
    563`_-compliant **deferred type hints** (i.e., type hints persisted as
    evaluatable strings rather than actual type hints) annotating this callable
    if any have been evaluated into actual type hints.

    Design
    ------
    This function does *not* bother caching **self-cached type hints** (i.e.,
    type hints that externally cache themselves), as these hints are already
    cached elsewhere. Self-cached type hints include most `PEP 484`_-compliant
    type hints declared by the :mod:`typing` module, which means that
    subscripting type hints declared by the :mod:`typing` module with the same
    child type hints reuses the exact same internally cached objects rather
    than creating new uncached objects: e.g.,

    .. code-block:: python

       >>> import typing
       >>> typing.List[int] is typing.List[int]
       True

    Equivalently, this function *only* caches **non-self-cached type hints**
    (i.e., type hints that do *not* externally cache themselves), as these
    hints are *not* already cached elsewhere. Non-self-cached type hints
    include *all* `PEP 585`_-compliant type hints produced by subscripting
    builtin container types, which means that subscripting builtin container
    types with the same child type hints creates new uncached objects rather
    than reusing the same internally cached objects: e.g.,

    .. code-block:: python

       >>> list[int] is list[int]
       False

    Motivation
    ----------
    This function enables callers to coerce non-self-cached type hints into
    :mod:`beartype`-cached type hints. :mod:`beartype` effectively requires
    *all* type hints to be cached somewhere! :mod:`beartype` does *not* care
    who, what, or how is caching those type hints -- only that they are cached
    before being passed to utility functions in the :mod:`beartype` codebase.
    Why? Because most such utility functions are memoized for efficiency by the
    :func:`beartype._util.cache.utilcachecall.callable_cached` decorator, which
    maps passed parameters (typically including the standard ``hint`` parameter
    accepting a type hint) based on object identity to previously cached return
    values. You see the problem, we trust.

    Non-self-cached type hints that are otherwise semantically equal are
    nonetheless distinct objects and will thus be treated as distinct
    parameters by memoization decorators. If this function did *not* exist,
    non-self-cached type hints could *not* be coerced into
    :mod:`beartype`-cached type hints and thus could *not* be memoized,
    reducing the efficiency of :mod:`beartype` for standard type hints.

    Parameters
    ----------
    func : Callable
        Callable annotated by this hint.
    pith_name : str
        Either:

        * If this hint annotates a parameter, the name of that parameter.
        * If this hint annotates the return, ``"return"``.
    hint : object
        Possibly non-self-cached and/or PEP-noncompliant type hint to be
        coerced and cached into the equivalent :mod:`beartype`-cached
        PEP-compliant type hint.
    hint_label : str
        Human-readable label describing this hint.

    Returns
    ----------
    object
        Either:

        * If this hint is either non-self-cached *or* PEP-noncompliant, the
          equivalent :mod:`beartype`-cached PEP-compliant type hint coerced and
          cached from this hint.
        * If this hint is self-cached *and* PEP-compliant, this hint as is.

    Raises
    ----------
    BeartypeDecorHintNonPepException
        If this object is neither:

        * A PEP-noncompliant type hint.
        * A supported PEP-compliant type hint.

    .. _PEP 484:
        https://www.python.org/dev/peps/pep-0484
    .. _PEP 563:
        https://www.python.org/dev/peps/pep-0563
    .. _PEP 585:
        https://www.python.org/dev/peps/pep-0585
    '''

    #FIXME: Call the new is_hint_pep_uncached() tester here to decide whether
    #or not to cache this hint.

    # If this hint is a PEP-noncompliant tuple union, coerce this union into
    # the equivalent PEP-compliant union subscripted by the same child hints.
    # By definition, PEP-compliant unions are a strict superset of
    # PEP-noncompliant tuple unions and thus accept all child hints accepted by
    # the latter.
    if isinstance(hint, tuple):
        assert callable(func), f'{repr(func)} not callable.'
        assert isinstance(pith_name, str), f'{pith_name} not string.'
        hint = func.__annotations__[pith_name] = Union.__getitem__(hint)
    # Else, this hint is *NOT* a PEP-noncompliant tuple union.

    # If this object is neither a PEP-noncompliant type hint *NOR* supported
    # PEP-compliant type hint, raise an exception.
    die_unless_hint(hint=hint, hint_label=hint_label)
    # Else, this object is either a PEP-noncompliant type hint *OR* supported
    # PEP-compliant type hint.

    # Return this hint.
    return hint