#!/usr/bin/env python3
# --------------------( LICENSE                           )--------------------
# Copyright (c) 2014-2020 Cecil Curry.
# See "LICENSE" for further details.

'''
**Beartype Python interpreter utilities.**

This private submodule implements supplementary interpreter-specific utility
functions required by various :mod:`beartype` facilities, including callables
generated by the :func:`beartype.beartype` decorator.

This private submodule is *not* intended for importation by downstream callers.
'''

# ....................{ IMPORTS                           }....................
import sys

# ....................{ CONSTANTS ~ at least              }....................
IS_PYTHON_AT_LEAST_4_0 = sys.version_info >= (4, 0)
'''
``True`` only if the active Python interpreter targets at least Python 4.0.0.
'''


#FIXME: After dropping Python 3.8 support:
#* Refactor all code conditionally testing this global to be unconditional.
#* Remove this global.
IS_PYTHON_AT_LEAST_3_9 = IS_PYTHON_AT_LEAST_4_0 or sys.version_info >= (3, 9)
'''
``True`` only if the active Python interpreter targets at least Python 3.8.0.
'''


#FIXME: After dropping Python 3.7 support:
#* Refactor all code conditionally testing this global to be unconditional.
#* Remove this global.
IS_PYTHON_AT_LEAST_3_8 = IS_PYTHON_AT_LEAST_3_9 or sys.version_info >= (3, 8)
'''
``True`` only if the active Python interpreter targets at least Python 3.8.0.
'''


#FIXME: After dropping Python 3.6 support:
#* Refactor all code conditionally testing this global to be unconditional.
#* Remove this global.
IS_PYTHON_AT_LEAST_3_7 = IS_PYTHON_AT_LEAST_3_8 or sys.version_info >= (3, 7)
'''
``True`` only if the active Python interpreter targets at least Python 3.7.0.
'''


#FIXME: After dropping Python 3.5 support:
#* Refactor all code conditionally testing this global to be unconditional.
#* Remove this global.
IS_PYTHON_AT_LEAST_3_6 = IS_PYTHON_AT_LEAST_3_7 or sys.version_info >= (3, 6)
'''
``True`` only if the active Python interpreter targets at least Python 3.6.0.
'''