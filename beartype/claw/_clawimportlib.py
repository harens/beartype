#!/usr/bin/env python3
# --------------------( LICENSE                            )--------------------
# Copyright (c) 2014-2022 Beartype authors.
# See "LICENSE" for further details.

'''
**Beartype all-at-once** :mod:`importlib` **machinery.**

This private submodule integrates high-level :mod:`importlib` machinery required
to implement :pep:`302`- and :pep:`451`-compliant import hooks with the
low-level abstract syntax tree (AST) transformation defined by the companion
:mod:`beartype.claw._clawast` submodule.

This private submodule is *not* intended for importation by downstream callers.
'''

# ....................{ TODO                               }....................
#FIXME: The New Five-Year Plan 2.0 is to avoid all interaction with the
#higher-level "sys.meta_path" mechanism entirely. Why? Because pytest leverages
#that some mechanism for its assertion rewriting. Do we care? *WE CARE,*
#especially because there appears to be no sensible means of portably stacking
#our own "MetaPathFinder" (...or whatever) on top of pytest's. Instead, we note
#the existence of the much less commonly used (but ultimately significantly
#safer) lower-level "sys.path_hooks" mechanism. Fascinatingly, AST transforms
#can be implemented by leveraging either. For some reason, everyone *ONLY*
#leverages the former to transform ASTs. Let's break that trend by instead
#leveraging the latter to transform ASTs. Specifically:
#* First, define a new private "_BeartypeSourceLoader(SourceFileLoader)" class
#  strongly inspired by the *SECOND* example of this exemplary StackOverflow
#  answer, which is probably the definitive statement on the subject:
#  https://stackoverflow.com/a/43573798/2809027
#  Note the use of the concrete "SourceFileLoader" superclass rather than the
#  less concrete "FileLoader" superclass. Since both typeguard and ideas
#  explicitly test for "SourceFileLoader" instances, it's almost certain that
#  that's what we require as well.
#  The disadvantage of this approach is that it fails to generalize to embedded
#  Python modules (e.g., in frozen archives or zip files). Of course, *SO DOES*
#  what "typeguard" and "ideas" are both doing and no one particularly seems to
#  care there, right? This approach is thus still generally robust enough to
#  suffice for a first pass.
#  After getting this simplistic approach working, let's then fully invest in
#  exhaustively testing that this approach successfully:
#  * Directly decorates callables declared at:
#    * Global scope in an on-disk top-level non-package module embedded in our
#      test suite.
#    * Class scope in the same module.
#    * Closure scope in the same module.
#  * Recursively decorates all callables declared by submodules of an on-disk
#    top-level package.
#  * Does *NOT* conflict with pytest's assertion rewriting mechanism. This will
#    be non-trivial. Can we isolate another pytest process within the main
#    currently running pytest process? O_o
#* Next, generalize that class to support stacking. What? Okay, so the core
#  issue with the prior approach is that it only works with standard Python
#  modules defined as standard files in standard directories. This assumption
#  breaks down for Python modules embedded within other files (e.g., as frozen
#  archives or zip files). The key insight here is given by Iguananaut in this
#  StackOverflow answer:
#    https://stackoverflow.com/a/48671982/2809027
#  This approach "...installs a special hook in sys.path_hooks that acts almost
#  as a sort of middle-ware between the PathFinder in sys.meta_path, and the
#  hooks in sys.path_hooks where, rather than just using the first hook that
#  says 'I can handle this path!' it tries all matching hooks in order, until it
#  finds one that actually returns a useful ModuleSpec from its find_spec
#  method."
#  Note that "hooks" in "sys.path_hooks" are actually *FACTORY FUNCTIONS*,
#  typically defined by calling the FileFinder.path_hook() class method.
#  We're unclear whether we want a full "ModuleSpec," however. It seems
#  preferable to merely search for a working hook in "sys.path_hooks" that
#  applies to the path. Additionally, if that hook defines a get_source() method
#  *AND* that method returns a non-empty string (i.e., that is neither "None"
#  *NOR* the empty string), then we want to munge that string with our AST
#  transformation. The advantages of this approach are multitude:
#  * This approach supports pytest, unlike standard "meta_path" approaches.
#  * This approach supports embedded files, unlike the first approach above. In
#    particular, note that the standard
#    "zipimporter.zipimporter(_bootstrap_external._LoaderBasics)" class for
#    loading Python modules from arbitrary zip files does *NOT* subclass any of
#    the standard superclasses you might expect it to (e.g.,
#    "importlib.machinery.SourceFileLoader"). Ergo, a simple inheritance check
#    fails to suffice. Thankfully, that class *DOES* define a get_source()
#    method resembling that of SourceFileLoader.get_source().
#FIXME: I've confirmed by deep inspection of both the standard "importlib"
#package and the third-party "_pytest.assertion.rewrite" subpackage that the
#above should (but possible does *NOT*) suffice to properly integrate with
#pytest. Notably, the
#_pytest.assertion.rewrite.AssertionRewritingHook.find_spec() class method
#improperly overwrites the "importlib._bootstrap.ModuleSpec.loader" instance
#variable with *ITSELF* here:
#
#    class AssertionRewritingHook(importlib.abc.MetaPathFinder, importlib.abc.Loader):
#        ...
#
#        _find_spec = importlib.machinery.PathFinder.find_spec
#
#        def find_spec(
#            self,
#            name: str,
#            path: Optional[Sequence[Union[str, bytes]]] = None,
#            target: Optional[types.ModuleType] = None,
#        ) -> Optional[importlib.machinery.ModuleSpec]:
#            ...
#
#            # *SO FAR, SO GOOD.* The "spec.loader" instance variable now refers
#            # to an instance of our custom "SourceFileLoader" subclass.
#            spec = self._find_spec(name, path)  # type: ignore
#            ...
#
#            # *EVEN BETTER.* This might save us. See below.
#            if not self._should_rewrite(name, fn, state):
#                return None
#
#            # And... everything goes to Heck right here. Passing "loader=self"
#            # completely replaces the loader that Python just helpfully
#            # provided with this "AssertionRewritingHook" instance, which is
#            # all manner of wrong.
#            return importlib.util.spec_from_file_location(
#                name,
#                fn,
#                loader=self,  # <-- *THIS IS THE PROBLEM, BRO.*
#                submodule_search_locations=spec.submodule_search_locations,
#            )
#
#Ultimately, it's no surprise whatsoever that this brute-force behaviour from
#pytest conflicts with everyone else in the Python ecosystem. That said, this
#might still not be an issue. Why? Because the call to self._should_rewrite()
#*SHOULD* cause "AssertionRewritingHook" to silently reduce to a noop for
#anything that beartype would care about.
#
#If true (which it should be), the above approach *SHOULD* still actually work.
#So why does pytest conflict with other AST transformation approaches? Because
#those other approaches also leverage "sys.meta_path" machinery, typically by
#forcefully prepending their own "MetaPathFinder" instance onto "sys.meta_path",
#which silently overwrites pytest's "MetaPathFinder" instance. Since we're *NOT*
#doing that, we should be fine with our approach. *sweat beads brow*

#FIXME: Improve module docstring, please.

# ....................{ IMPORTS                            }....................
from ast import (
    PyCF_ONLY_AST,
    fix_missing_locations,
)
from beartype.claw._clawast import _BeartypeNodeTransformer
from beartype.roar import BeartypeClawRegistrationException
from beartype.typing import (
    Dict,
    Iterable,
    Optional,
    Union,
)
from beartype._conf import BeartypeConf
from beartype._util.func.utilfunccodeobj import (
    FUNC_CODEOBJ_NAME_MODULE,
    get_func_codeobj,
)
from beartype._util.func.utilfuncframe import get_frame
from beartype._util.text.utiltextident import is_identifier
from collections.abc import Iterable as IterableABC
from importlib import invalidate_caches
from importlib.machinery import (
    SOURCE_SUFFIXES,
    FileFinder,
    SourceFileLoader,
)
from importlib.util import (
    cache_from_source,
    decode_source,
)
from sys import (
    path_hooks,
    path_importer_cache,
)
from threading import RLock
from types import (
    CodeType,
    FrameType,
)

# See the "beartype.cave" submodule for further commentary.
__all__ = ['STAR_IMPORTS_CONSIDERED_HARMFUL']

# ....................{ PRIVATE ~ globals : packages       }....................
#FIXME: Ideally, the type hint annotating this global would be defined as a
#recursive type alias ala:
#    _PackageBasenameToSubpackages = (
#        Dict[str, Optional['_PackageBasenameToSubpackages']])
#Sadly, mypy currently fails to support recursive type aliases. Ergo, we
#currently fallback to a simplistic alternative whose recursion "bottoms out"
#at the first nested dictionary. See also:
#    https://github.com/python/mypy/issues/731
_PackageBasenameToSubpackages = (
    Dict[str, Optional[dict]])
'''
PEP-compliant type hint matching the recursively nested data structure of the
private :data:`_package_basename_to_subpackages` global.
'''


#FIXME: Still not quite right. We also want to associate "BeartypeConf" settings
#with hooked package names. Ergo, we need a companion flat dictionary ala:
#    _package_name_to_conf = {
#        'a': BeartypeConf(...),
#        'a.b': BeartypeConf(...),
#        'a.c': BeartypeConf(...),
#        'z': BeartypeConf(...),
#    }
#
#To decide whether a package name is being beartyped, we'll still leverage the
#"_package_basename_to_subpackages" dictionary for efficiency. Once we've
#decided that, we'll decide the configuration for that package by iteratively:
#* If the name of that package is a key of "_package_name_to_conf", use the
#  associated value as that package's configuration.
#* Else, strip the rightmost subpackage name from that package name and repeat.
#
#Thankfully, note that search is still worst-case O(h) time for "h" the height
#of the "_package_basename_to_subpackages" dictionary. Phew.

_package_basename_to_subpackages: _PackageBasenameToSubpackages = {}
'''
Non-thread-safe dictionary mapping in a recursively nested manner from the
unqualified basename of each subpackage to be subsequently possibly type-checked
on first importation by the :func:`beartype.beartype` decorator to either the
``None`` singleton if that subpackage is to be type-checked *or* a nested
dictionary satisfying the same structure otherwise (i.e., if that subpackage is
*not* to be type-checked).

Motivation
----------
This dictionary is intentionally structured as a non-trivial nested data
structure rather than a trivial non-nested flat dictionary. Why? Efficiency.
Consider this flattened set of package names:

    .. code-block:: python

       _package_names = {'a.b', 'a.c', 'd'}

Deciding whether an arbitrary package name is in that set or not requires
worst-case ``O(n)`` iteration across the set of ``n`` package names.

Consider instead this nested dictionary whose keys are package names split on
``.`` delimiters and whose values are either recursively nested dictionaries of
the same format *or* the ``None`` singleton (terminating the current package
name):

    .. code-block:: python

       _package_basename_to_subpackages = {
           'a': {'b': None, 'c': None}, 'd': None}

Deciding whether an arbitrary package name is in this dictionary or not requires
worst-case ``O(h)`` iteration across the height ``h`` of this dictionary
(equivalent to the largest number of ``.`` delimiters for any fully-qualified
package name encapsulated by this dictionary). Since ``h <<<<<<<<<< n``, this
dictionary provides substantially faster worst-case lookup than that set.

Moreover, in the worst case:

* That set requires one inefficient string prefix test for each item.
* This dictionary requires *only* one efficient string equality test for each
  nested key-value pair while descending towards the target package name.

Let's do this, fam.

Caveats
----------
**This global is only safely accessible in a thread-safe manner from within a**
``with _globals_lock:`` **context manager.** Ergo, this global is *not* safely
accessible outside that context manager.

Examples
----------
Instance of this data structure type-checking on import submodules of the root
``package_z`` package, the child ``package_a.subpackage_k`` submodule, and the
``package_a.subpackage_b.subpackage_c`` and
``package_a.subpackage_b.subpackage_d`` submodules:

    >>> _package_basename_to_subpackages = {
    ...     'package_a': {
    ...         'subpackage_b': {
    ...             'subpackage_c': None,
    ...             'subpackage_d': None,
    ...         },
    ...         'subpackage_k': None,
    ...     },
    ...     'package_z': None,
    ... }
'''

# ....................{ PRIVATE ~ globals : threading      }....................
_globals_lock = RLock()
'''
Reentrant reusable thread-safe context manager gating access to otherwise
non-thread-safe private globals defined by this submodule (e.g.,
:data:`_package_basename_to_subpackages`).
'''

# ....................{ HOOKS                              }....................
#FIXME: *NOT RIGHT.* Repeated calls of this function from multiple third-party
#packages currently add multiple closures to "sys.path_hooks", which is insane.
#Instead:
#* The first call to this function from anywhere should do what we currently do,
#  which is to add our "loader_factory" closure to "sys.path_hooks".
#* Each subsequent call to this function should *DO ABSOLUTELY NOTHING* aside
#  from adding the passed packages names to our global list of such packages.
#
#Thankfully, distinguishing between the two is trivial: if
#"_package_basename_to_subpackages" is empty, this is the first call to this
#function and our "loader_factory" closure should be added to "sys.path_hooks".
#FIXME: Unit test us up, please.
#FIXME: Define a comparable removal function named either:
#* cancel_beartype_submodules_on_import(). This is ostensibly the most
#  unambiguous and thus the best choice of those listed here. Obviously,
#  beartype_submodules_on_import_cancel() is a comparable alternative.
#* forget_beartype_on_import().
#* no_beartype_on_import().
def beartype_submodules_on_import(
    # Optional parameters.
    package_names: Optional[Iterable[str]] = None,

    # Optional keyword-only parameters.
    *,
    conf: BeartypeConf = BeartypeConf(),
) -> None:
    '''
    Register a new **beartype import path hook** (i.e., callable inserted to the
    front of the standard :mod:`sys.path_hooks` list recursively applying the
    :func:`beartype.beartype` decorator to all well-typed callables and classes
    defined by all submodules of all packages with the passed names on the first
    importation of those submodules).

    Parameters
    ----------
    package_names : Optional[Iterable[str]]
        Iterable of the fully-qualified names of one or more packages to be
        type-checked by :func:`beartype.beartype`. Defaults to ``None``, in
        which case this parameter defaults to a 1-tuple containing only the
        fully-qualified name of the **calling package** (i.e., external parent
        package of the submodule directly calling this function).
    conf : BeartypeConf, optional
        **Beartype configuration** (i.e., self-caching dataclass encapsulating
        all settings configuring type-checking for the passed object). Defaults
        to ``BeartypeConf()``, the default ``O(1)`` constant-time configuration.

    See Also
    ----------
    https://stackoverflow.com/a/43573798/2809027
        StackOverflow answer strongly inspiring the low-level implementation of
        this function with respect to inscrutable :mod:`importlib` machinery.
    '''

    # ..................{ PACKAGE NAMES                      }..................
    # Note the following logic *CANNOT* reasonably be isolated to a new
    # private helper function. Why? Because this logic itself calls existing
    # private helper functions assuming the caller to be at the expected
    # position on the current call stack.
    if package_names is None:
        #FIXME: *UNSAFE.* get_frame() raises a "ValueError" exception if
        #passed a non-existent frame, which is non-ideal: e.g.,
        #    >>> sys._getframe(20)
        #    ValueError: call stack is not deep enough
        #Since beartype_on_import() is public, that function can
        #technically be called directly from a REPL. When it is, a
        #human-readable exception should be raised instead. Notably, we
        #instead want to:
        #* Define new utilfuncframe getters resembling:
        #      def get_frame_or_none(ignore_frames: int) -> Optional[FrameType]:
        #          try:
        #              return get_frame(ignore_frames + 1)
        #          except ValueError:
        #              return None
        #      def get_frame_caller_or_none() -> Optional[FrameType]:
        #          return get_frame_or_none(2)
        #* Import "get_frame_caller_or_none" above.
        #* Refactor this logic here to resemble:
        #      frame_caller = get_frame_caller_or_none()
        #      if frame_caller is None:
        #          raise BeartypeClawRegistrationException(
        #              'beartype_submodules_on_import() '
        #              'not callable directly from REPL scope.'
        #          )
        frame_caller: FrameType = get_frame(1)  # type: ignore[assignment,misc]

        # Code object underlying the caller if that caller is pure-Python *OR*
        # raise an exception otherwise (i.e., if that caller is C-based).
        frame_caller_codeobj = get_func_codeobj(frame_caller)

        # Unqualified basename of that caller.
        frame_caller_basename = frame_caller_codeobj.co_name

        # Fully-qualified name of the module defining that caller.
        frame_caller_module_name = frame_caller.f_globals['__name__']

        #FIXME: Relax this constraint, please. Just iteratively search up the
        #call stack with iter_frames() until stumbling into a frame satisfying
        #this condition.
        # If that name is *NOT* the placeholder string assigned by the active
        # Python interpreter to all scopes encapsulating the top-most lexical
        # scope of a module in the current call stack, the caller is a class or
        # callable rather than a module. In this case, raise an exception.
        if frame_caller_basename != FUNC_CODEOBJ_NAME_MODULE:
            raise BeartypeClawRegistrationException(
                f'beartype_submodules_on_import() '
                f'neither passed "package_names" nor called from module scope '
                f'(i.e., caller scope '
                f'"{frame_caller_module_name}.{frame_caller_basename}" '
                f'either class or callable). '
                f'Please either pass "package_names" or '
                f'call this function from module scope.'
            )

        # If the fully-qualified name of the module defining that caller
        # contains *NO* delimiters, that module is a top-level module defined by
        # *NO* parent package. In this case, raise an exception. Why? Because
        # this function uselessly and silently reduces to a noop when called by
        # a top-level module. Why? Because this function registers an import
        # hook applicable only to subsequently imported submodules of the passed
        # packages. By definition, a top-level module is *NOT* a package and
        # thus has *NO* submodules. To prevent confusion, notify the user here.
        #
        # Note this is constraint is also implicitly imposed by the subsequent
        # call to the frame_caller_module_name.rpartition() method: e.g.,
        #     >>> frame_caller_module_name = 'muh_module'
        #     >>> frame_caller_module_name.rpartition()
        #     ('', '', 'muh_module')  # <-- we're now in trouble, folks
        if '.' not in frame_caller_module_name:
            raise BeartypeClawRegistrationException(
                f'beartype_submodules_on_import() '
                f'neither passed "package_names" nor called by a submodule '
                f'(i.e., caller module "{frame_caller_module_name}" '
                f'defined by no parent package).'
            )
        # Else, that module is a submodule of some parent package.

        # Fully-qualified name of the parent package defining that submodule,
        # parsed from the name of that submodule via this standard idiom:
        #     >>> frame_caller_module_name = 'muh_package.muh_module'
        #     >>> frame_caller_module_name.rpartition()
        #     ('muh_package', '.', 'muh_module')
        frame_caller_package_name = frame_caller_module_name.rpartition()[0]

        # Default this iterable to the 1-tuple referencing only this package.
        package_names = (frame_caller_package_name,)

    # If this iterable of package names is *NOT* an iterable, raise an
    # exception.
    if not isinstance(package_names, IterableABC):
        raise BeartypeClawRegistrationException(
            f'Package names {repr(package_names)} not iterable.')
    # Else, this iterable of package names is an iterable.
    #
    # If this iterable of package names is empty, raise an exception.
    elif not package_names:
        raise BeartypeClawRegistrationException('Package names empty.')
    # Else, this iterable of package names is non-empty.

    # For each such package name...
    for package_name in package_names:
        # If this package name is *NOT* a string, raise an exception.
        if not isinstance(package_name, str):
            raise BeartypeClawRegistrationException(
                f'Package name {repr(package_name)} not string.')
        # Else, this package name is a string.
        #
        # If this package name is *NOT* a valid Python identifier, raise an
        # exception.
        elif not is_identifier(package_name):
            raise BeartypeClawRegistrationException(
                f'Package name {repr(package_name)} invalid (i.e., not '
                f'"."-delimited Python identifier).'
            )
        # Else, this package name is a valid Python identifier.

    #FIXME: Validate the passed "conf" parameter here, please.

    #FIXME: Pass "package_names" to _BeartypeMetaPathFinder(), please. Uhm...
    #how exactly do we do that, though? *OH. OH, BOY.* The
    #FileFinder.path_hook() creates a closure that, when invoked, ultimately
    #calls the FileFinder._get_spec() method that instantiates our loader in the
    #bog-standard way ala:
    #    loader = loader_class(fullname, path)
    #So, that doesn't leave us with any means of intervening in the process.
    #We have two options here:
    #* [CRUDE OPTION] The crude option is to cache all passed package names into
    #  a new private global thread-safe "_package_names" list, which can only be
    #  safely accessed by a "threading.{R,}Lock" context manager. Each
    #  "_BeartypeSourceFileLoader" instance then accesses that global list. This
    #  isn't necessarily awful. That said...
    #* [FINE OPTION] The fine option is to do what we probably already want to
    #  do and adopt the stacking solution described both above and at:
    #      https://stackoverflow.com/a/48671982/2809027
    #  This approach requires considerably more work, because we then need to
    #  completely avoid all existing "importlib" machinery and write our own.
    #  That's not necessarily a bad thing, though -- because all that machinery
    #  is insufficient for our needs, anyway! So, we should probably "just do
    #  the right thing" and adopt the fine solution. It's fine, yo.
    #FIXME: Actually, just do the global thread-safe
    #"package_basename_to_subpackages" approach for now. See below!

    # ..................{ PATH HOOK                          }..................
    # 2-tuple of the undocumented format expected by the FileFinder.path_hook()
    # class method called below, associating our beartype-specific source file
    # loader with the platform-specific filetypes of all sourceful Python
    # packages and modules. We didn't do it. Don't blame the bear.
    LOADER_DETAILS = (_BeartypeSourceFileLoader, SOURCE_SUFFIXES)

    # Closure instantiating a new "FileFinder" instance invoking this loader.
    #
    # Note that we intentionally ignore mypy complaints here. Why? Because mypy
    # erroneously believes this method accepts 2-tuples whose first items are
    # loader *INSTANCES* (e.g., "Tuple[Loader, List[str]]"). In fact, this
    # method accepts 2-tuples whose first items are loader *TYPES* (e.g.,
    # "Tuple[Type[Loader], List[str]]"). This is why we can't have nice.
    loader_factory = FileFinder.path_hook(LOADER_DETAILS)  # type: ignore[arg-type]

    # Prepend a new import hook (i.e., factory closure encapsulating this
    # loader) *BEFORE* all other import hooks.
    path_hooks.insert(0, loader_factory)

    # Uncache *ALL* competing loaders cached by prior importations. Just do it!
    path_importer_cache.clear()
    invalidate_caches()

# ....................{ PRIVATE ~ classes                  }....................
#FIXME: *PROBABLY INSUFFICIENT.* For safety, we really only want to apply this
#loader to packages in the passed "package_names" list. For all other packages,
#the relevant method of this loader (which is probably find_spec(), but let's
#research that further) should return "None". Doing so defers loading to the
#next loader in "sys.path_hooks".
#FIXME: Unit test us up, please.
class _BeartypeSourceFileLoader(SourceFileLoader):
    '''
    **Beartype source file loader** implementing :mod:`importlib` machinery
    loading a **sourceful Python package or module** (i.e., package or module
    backed by a ``.py``-suffixed source file) into a **module spec** (i.e.,
    in-memory :class:`importlib._bootstrap.ModuleSpec` instance describing the
    importation of that package or module, complete with a reference back to
    this originating loader).

    The :func:`beartype_package` function injects a low-level **import path
    hook** (i.e., factory closure instantiating this class as an item of the
    standard :mod:`sys.path_hooks` list) to the front of that list. When called
    by a higher-level parent **import metapath hook** (i.e., object suitable for
    use as an item of the standard :mod:`sys.meta_path` list), that closure:

    #. Instantiates one instance of this class for each **imported Python
       package or module** (i.e., package or module on the standard
       :mod:`sys.path` list).
    #. Adds a new key-value pair to the standard :mod:`sys.path_importer_cache`
       dictionary, whose:

       * Key is the package of that module.
       * Value is that instance of this class.

    See Also
    ----------
    * The `comparable "typeguard.importhook" submodule <typeguard import
      hook_>`__ implemented by the incomparable `@agronholm (Alex Grönholm)
      <agronholm_>`__, whose intrepid solutions strongly inspired this
      subpackage. `Typeguard's import hook infrastructure <typeguard import
      hook_>`__ is a significant improvement over the prior state of the art in
      Python and a genuine marvel of concise, elegant, and portable abstract
      syntax tree (AST) transformation.

    .. _agronholm:
       https://github.com/agronholm
    .. _typeguard import hook:
       https://github.com/agronholm/typeguard/blob/master/src/typeguard/importhook.py
    '''

    # ..................{ API                                }..................
    #FIXME: We also need to also:
    #* Define the find_spec() method, which should:
    #  * Efficiently test whether the passed "path" is in "_package_names" in a
    #    *THREAD-SAFE MANNER.*
    #  * If not, this method should reduce to a noop by returning "None".
    #  * Else, this method should return the value of calling the superclass
    #    find_spec() implementation.
    #  We're fairly certain that suffices. Nonetheless, verify this by
    #  inspecting the comparable find_spec() implementation at:
    #      https://stackoverflow.com/a/48671982/2809027
    #* Monkey-patch the exec_module() method, please. Maybe? Is there truly no
    #  saner means of doing so? I've confirmed that "importlib" machinery
    #  elsewhere directly calls "loader.exec_module()", so... we probably have
    #  no safe alternative. It is what it is. Look! Just do this, fam. \o/

    # Note that we explicitly ignore mypy override complaints here. For unknown
    # reasons, mypy believes that "importlib.machinery.SourceFileLoader"
    # subclasses comply with the "importlib.abc.InspectLoader" abstract base
    # class (ABC). Of course, this is *NOT* the case. Ergo, we entirely ignore
    # mypy complaints here with respect to signature matching.
    def source_to_code(  # type: ignore[override]
        self,

        # Mandatory parameters.
        data: bytes,
        path: str,

        # Optional keyword-only parameters.
        *,
        _optimize: int =-1,
    ) -> CodeType:
        '''
        Code object dynamically compiled from the **sourceful Python package or
        module** (i.e., package or module backed by a ``.py``-suffixed source
        file) with the passed undecoded contents and filename, efficiently
        transformed in-place by our abstract syntax tree (AST) transformation
        automatically applying the :func:`beartype.beartype` decorator to all
        applicable objects of that package or module.

        Parameters
        ----------
        data : bytes
            **Byte array** (i.e., undecoded list of bytes) of the Python package
            or module to be decoded and dynamically compiled into a code object.
        path : str
            Absolute or relative filename of that Python package or module.
        _optimize : int, optional
            **Optimization level** (i.e., numeric integer signifying increasing
            levels of optimization under which to compile that Python package or
            module). Defaults to -1, implying the current interpreter-wide
            optimization level with which the active Python process was
            initially invoked (e.g., via the ``-o`` command-line option).

        Returns
        ----------
        CodeType
            Code object dynamically compiled from that Python package or module.
        '''

        # Plaintext decoded contents of that package or module.
        module_source = decode_source(data)

        # Abstract syntax tree (AST) dynamically parsed from these contents.
        module_ast = compile(
            module_source,
            path,
            'exec',
            PyCF_ONLY_AST,
            dont_inherit=True,
            optimize=_optimize,
        )

        # Abstract syntax tree (AST) modified by our AST transformation dynamically parsed from these contents.
        module_ast_beartyped = _BeartypeNodeTransformer().visit(module_ast)

        #FIXME: Document why exactly this call is needed -- if indeed this call
        #is needed. Is it? Research us up, please.
        fix_missing_locations(module_ast_beartyped)

        # Code object dynamically compiled from that transformed AST.
        module_codeobj = compile(
            module_ast_beartyped,
            path,
            'exec',
            dont_inherit=True,
            optimize=_optimize,
        )

        # Return this code object.
        return module_codeobj