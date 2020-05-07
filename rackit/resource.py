"""
Module containing the resource base class for rackit.
"""

from collections import namedtuple, UserDict
import copy
import pprint

from .manager import ResourceManager


def _merge(obj1, obj2):
    """
    Merge two objects together.

    If obj1 and obj2 are dictionaries, they are recursively merged, with keys from
    obj2 taking precedence.

    If obj1 and obj2 are lists or tuples, they are concatenated.

    In all other cases, obj2 is returned.
    """
    if isinstance(obj1, dict):
        merged = copy.deepcopy(obj1)
        for k, v in obj2.items():
            if k in merged:
                merged[k] = _merge(merged[k], v)
            else:
                merged[k] = v
        return merged
    elif isinstance(obj1, (list, tuple)):
        return tuple(obj1) + tuple(obj2)
    else:
        return obj2


class Options:
    """
    Object for containing and accessing resource options.
    """
    def __init__(self, options = None):
        self._options = options or dict()

    def __getattr__(self, name):
        try:
            return self._options[name]
        except KeyError:
            message = "'{}' object has no attribute '{}'".format(
                self.__class__.__name__,
                name
            )
            raise AttributeError(message)

    def _update(self, **options):
        """
        Returns a new options object consisting of these options
        recursively merged with the given options.
        """
        return Options(_merge(self._options, options))


class ResourceMeta(type):
    """
    Metaclass for :py:class:`Resource`.

    Allows the definition of options using a nested meta class. The given options are
    merged with those from parent classes.
    """
    def __new__(mcs, name, bases, attrs):
        # Pop the nested options class for later
        meta = attrs.pop('Meta', None)
        # Create the resource class
        resource_cls = super().__new__(mcs, name, bases, attrs)
        # Get the current options
        prev_options = getattr(resource_cls, '_opts', Options())
        # Extract the new options from the nested class
        new_options = { k: v for k, v in vars(meta).items() if not k.startswith('__') }
        # Update the options for the new class
        resource_cls._opts = prev_options._update(**new_options)
        return resource_cls


class Resource(metaclass = ResourceMeta):
    """
    Base class for a resource instance returned from an API, providing readonly attribute-
    and dict-style access to the underlying data.

    Resource instances are aware of the manager that created them, which means
    they can call methods on the manager if required. In particular, this allows an
    instance to be marked as 'partial', which means any attempt to access a missing
    attribute/key triggers a fetch by key using the manager.
    """
    class Meta:
        #: The manager class for the resource
        manager_cls = ResourceManager
        #: Indicates if listing returns partial entities that should be lazily loaded
        list_partial = False
        #: The endpoint for the resource
        endpoint = None
        #: The name of the field to use as the primary key
        #: The default is to use the id of the resource
        primary_key_field = 'id'
        #: A dictionary of attribute aliases in the form ``alias => target``
        aliases = dict()
        #: A list or tuple of additional cache keys for the resource
        #: If a field is unique, it can be added here to save unnecessary fetches
        cache_keys = tuple()

    def __init__(self, manager, data, partial = False, path = None, parent = None):
        self._manager = manager
        self._data = data
        self._partial = partial
        # By default, get the path and parent from the manager, but allow them
        # to be overridden
        self._path = path or self._manager.prepare_url(self._primary_key)
        self._parent = parent or self._manager.parent
        self._nested_managers = {}

    def __hash__(self):
        return hash(self._primary_key)

    def __eq__(self, other):
        # Two resources are equal if they are of the same type with the same data
        return isinstance(other, type(self)) and self._data == other._data

    @property
    def _primary_key(self):
        """
        Returns the primary key for the resource. This is the key that is used in URLs,
        and as a cache key.

        By default, the field specified by the ``primary_key_field`` is used.
        """
        return self[self._opts.primary_key_field]

    def _nested_manager(self, resource_cls):
        """
        Return the first nested manager for the given resource class, if there is one,
        or ``None`` if one does not exist.
        """
        from .descriptors import NestedResource
        # Traverse the properties of this resource class looking for the first resource
        # manager descriptor with the correct resource class, then evaluate it for this
        # instance
        if resource_cls not in self._nested_managers:
            try:
                self._nested_managers[resource_cls] = next(
                    getattr(self, name)
                    for name, d in type(self).__dict__.items()
                    if isinstance(d, NestedResource) and
                       issubclass(d.resource_cls, resource_cls)
                )
            except StopIteration:
                return None
        return self._nested_managers[resource_cls]

    def __getitem__(self, key):
        # Map the key using the aliases
        orig_key = key
        key = self._opts.aliases.get(key, key)
        # If we don't have the key but are in partial mode, attempt a load
        if key not in self._data and self._partial:
            # Force the instance to load from the stored path and copy the data over
            self._data = self._manager._load(self._path)._data.copy()
            # We are no longer partial
            self._partial = False
        try:
            return self._data[key]
        except KeyError as exc:
            # Map key errors for the value back onto the original key
            if str(exc) == "'{}'".format(key):
                raise KeyError(orig_key)
            else:
                raise

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            # Only convert key errors that match the name that was asked for
            if str(exc) == "'{}'".format(name):
                message = "'{}' object has no attribute '{}'".format(
                    self.__class__.__name__,
                    name
                )
                raise AttributeError(message)
            else:
                raise

    def _update(self, **params):
        """
        Return a new resource instance by updating this instance with the given parameters.
        """
        return self._manager.update(self, **params)

    def _delete(self):
        """
        Delete this resource instance.
        """
        return self._manager.delete(self)

    def _action(self, action, **params):
        """
        Executes the specified action on this resource instance.
        """
        return self._manager.action(self, action, **params)

    def __repr__(self):
        klass = self.__class__
        return '{}.{}({})'.format(klass.__module__, klass.__qualname__, repr(self._data))


def pprint_resource(printer, object, stream, indent, allowance, context, level):
    """
    Hook for the pprint module that allows pretty-printing of resources.
    """
    write = stream.write
    klass = object.__class__
    class_name = "{}.{}".format(klass.__module__, klass.__qualname__)
    write(class_name + '({\n')
    if len(object._data):
        write(' ' * (indent + printer._indent_per_level))
        printer._format_dict_items(
            object._data.items(),
            stream,
            indent,
            allowance + 1,
            context,
            level
        )
        write('\n')
    write(indent * ' ' + '})')


# Register the hook with pprint
pprint.PrettyPrinter._dispatch[Resource.__repr__] = pprint_resource
