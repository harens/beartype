#!/usr/bin/env python3
# --------------------( LICENSE                            )--------------------
# Copyright (c) 2014-2022 Beartype authors.
# See "LICENSE" for further details.

'''
Project-wide **beartype-generated wrapper function utilities** (i.e., callables
specifically applicable to wrapper functions generated by the
:func:`beartype.beartype` decorator for beartype-decorated callables).

This private submodule is *not* intended for importation by downstream callers.
'''

# ....................{ IMPORTS                            }....................
from beartype._util.func.pep.utilpep484func import (
    is_func_pep484_notypechecked)
from beartype._util.mod.lib.utilsphinx import is_sphinx_autodocing
from collections.abc import Callable

# ....................{ TESTERS                            }....................
#FIXME: Unit test us up, please.
def is_func_unbeartypeable(func: Callable) -> bool:
    '''
    ``True`` only if the passed callable is a **unbeartypeable** (i.e., if the
    :func:`beartype.beartype` decorator should preserve that callable as is by
    reducing to the identity decorator rather than wrap that callable with
    constant-time type-checking).

    Parameters
    ----------
    func : Callable
        Callable to be inspected.

    Returns
    ----------
    bool
        ``True`` only if that callable is unbeartypeable.
    '''

    # Return true only if either...
    return (
        # This callable is unannotated *OR*...
        not func.__annotations__ or
        # This callable is decorated by the @typing.no_type_check decorator
        # defining this dunder instance variable on this callable *OR*...
        is_func_pep484_notypechecked(func) or
        # This callable is a @beartype-specific wrapper previously generated by
        # this decorator *OR*...
        is_func_beartyped(func) or
        # Sphinx is currently autogenerating documentation (i.e., if this
        # decorator has been called from a Python call stack invoked by the
        # "autodoc" extension bundled with the optional third-party build-time
        # "sphinx" package)...
        #
        # Why? Because of mocking. When @beartype-decorated callables are
        # annotated with one more classes mocked by "autodoc_mock_imports",
        # @beartype frequently raises exceptions at decoration time. Why?
        # Because mocking subverts our assumptions and expectations about
        # classes used as annotations.
        is_sphinx_autodocing()
    )


def is_func_beartyped(func: Callable) -> bool:
    '''
    ``True`` only if the passed callable is a **beartype-generated wrapper
    function** (i.e., function dynamically generated by the
    :func:`beartype.beartype` decorator for a user-defined callable decorated by
    that decorator, wrapping that callable with constant-time type-checking).

    Parameters
    ----------
    func : Callable
        Callable to be inspected.

    Returns
    ----------
    bool
        ``True`` only if that callable is a beartype-generated wrapper function.
    '''

    # Return true only if this callable is a @beartype-specific wrapper
    # previously generated by this decorator.
    return hasattr(func, '__beartype_wrapper')

# ....................{ SETTERS                            }....................
def set_func_beartyped(func: Callable) -> None:
    '''
    Declare the passed callable to be a **beartype-generated wrapper function**
    (i.e., function dynamically generated by the :func:`beartype.beartype`
    decorator for a user-defined callable decorated by that decorator, wrapping
    that callable with constant-time type-checking).

    Parameters
    ----------
    func : Callable
        Callable to be modified.
    '''

    # Declare this callable to be generated by @beartype, which tests for the
    # existence of this attribute above to avoid re-decorating callables
    # already decorated by @beartype by efficiently reducing to a noop.
    func.__beartype_wrapper = True  # type: ignore[attr-defined]
