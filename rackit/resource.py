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
        return self.__class__(_merge(self._options, options))

    def _cast(self, options_cls):
        """
        Cast these options to a new options class.
        """
        return options_cls(self._options)


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
        if meta:
            # Start with the options as set by the parent class
            options = getattr(resource_cls, '_opts', Options())
            # Extract the new options from the nested class
            new_options = { k: v for k, v in vars(meta).items() if not k.startswith('__') }
            # If the meta sets a new options class, cast the current options to it
            options_cls = new_options.pop('options_cls', None)
            if options_cls:
                options = options._cast(options_cls)
            # Update the options for the new class
            resource_cls._opts = options._update(**new_options)
        return resource_cls


class UnmanagedResource(metaclass = ResourceMeta):
    """
    Base class for a resource returned from an API endpoint.

    It provides readonly attribute- and dict-style access to the underlying data, and
    can be lazily loaded.

    REST semantics are not imposed here, and the resource does not have a manager.
    Instead, it consumes the connection directly, and just loads data directly from the
    configured endpoint.

    This type of resource does not have REST semantics, and cannot be used with the
    :py:class:`.descriptors.RootResource` or :py:class:`.descriptors.NestedResource`
    descriptors. However, it can be used with the :py:class:`.descriptors.EmbeddedResource`
    descriptor and attached to connections using the :py:class:`.descriptors.Endpoint`
    descriptor.
    """
    class Meta:
        #: The options class to use for the resource
        options_cls = Options
        #: The endpoint for the resource
        endpoint = None
        #: A dictionary of attribute aliases in the form ``alias => target``
        aliases = dict()
        #: A dictionary of defaults in the form ``key => default``
        defaults = dict()
        #: The HTTP verb used for updates
        update_http_verb = 'PATCH'

    def __init__(self, connection, data, partial = False, path = None):
        self._connection = connection
        self._data = data
        self._partial = partial
        self._path = path or self._opts.endpoint

    def __hash__(self):
        # Take a hash of the data
        return hash(self._data)

    def __eq__(self, other):
        # Two resources are equal if they are of the same type with the same data
        return isinstance(other, type(self)) and self._data == other._data

    def _fetch(self):
        """
        Fetch the data from the specified endpoint.
        """
        # If there is no path, just return the current data rather than fetching
        if self._path:
            return self._connection.api_get(self._path).json()
        else:
            return self._data

    def _get_default(self, key):
        """
        Returns the default value for the key.
        """
        default = self._opts.defaults[key]
        return default() if callable(default) else default

    def __getitem__(self, key):
        # If we don't have the key but are in partial mode, attempt a load
        if key not in self._data and self._partial:
            # Force the instance to load
            self._data = self._fetch()
            # We are no longer partial
            self._partial = False
        try:
            return self._data[key]
        except KeyError:
            # This might raise another key error, which is fine
            return self._get_default(key)

    def __getattr__(self, name):
        # Map the attribute name to a data key using the aliases
        key = self._opts.aliases.get(name, name)
        # Convert any key errors into attribute errors for the requested name
        try:
            return self[key]
        except KeyError:
            message = "'{}' object has no attribute '{}'".format(
                self.__class__.__name__,
                name
            )
            raise AttributeError(message)

    def __repr__(self):
        klass = self.__class__
        return '{}.{}({})'.format(klass.__module__, klass.__qualname__, repr(self._data))

    def _update(self, params = None, **kwargs):
        """
        Update the resource with the given parameters.
        """
        # Combine the params and kwargs to get the parameters
        params = params.copy() if params else dict()
        params.update(kwargs)
        # Decide which verb to use to update the resource
        verb = self._opts.update_http_verb.lower()
        method = getattr(self._connection, 'api_{}'.format(verb))
        response = method(self._path, json = params)
        return self.__class__(self._connection, response.json(), path = self._path)

    def _delete(self, resource_or_key):
        """
        Delete the given resource instance or key.
        """
        self._connection.api_delete(self._path)

    def _as_dict(self):
        # If the instance is partial, force a fetch before returning
        if self._partial:
            self._data = self._fetch()
            self._partial = False
        return copy.deepcopy(self._data)


class Resource(UnmanagedResource):
    """
    Base class for a managed resource returned from an API.

    This imposes REST-style semantics on top of :py:class:`UnmanagedResource`, including
    the assumption that each resource has a stable unique id. This enables more advanced
    features like REST semantics, caching and nested resources.

    Managed resources are aware of the manager that created them, which means
    they can call methods on the manager if required. This can be used to implement
    "smart" resources that can invoke actions using the manager.
    """
    class Meta:
        #: The manager class for the resource
        manager_cls = ResourceManager
        #: Indicates if listing returns partial entities that should be lazily loaded
        list_partial = False
        #: The name of the field to use as the primary key
        #: The default is to use the id of the resource
        primary_key_field = 'id'
        #: A list or tuple of additional cache keys for the resource
        #: If a field is unique, it can be added here to save unnecessary fetches
        cache_keys = tuple()

    def __init__(self, manager, data, partial = False, path = None, parent = None):
        self._manager = manager
        # As long as we set data and partial, we don't need to call the super __init__
        self._data = data
        self._partial = partial
        # By default, get the path and parent from the manager, but allow them
        # to be overridden
        self._path = path or manager.prepare_url(self._primary_key)
        self._parent = parent or manager.parent
        self._nested_managers = {}

    def __hash__(self):
        # We can just use the hash of the primary key
        return hash(self._primary_key)

    @property
    def _primary_key(self):
        """
        Returns the primary key for the resource. This is the key that is used in URLs,
        and as a cache key.

        By default, the field specified by the ``primary_key_field`` is used.
        """
        return self[self._opts.primary_key_field]

    def _fetch(self):
        # Use the manager to fetch the instance instead of the connection
        # This allows us to benefit from caching, but we have to be careful to take an
        # independent copy of the data in case it did come from cache
        return self._manager._load(self._path)._data.copy()

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

    def _update(self, params = None, **kwargs):
        """
        Return a new resource instance by updating this instance with the given parameters.
        """
        return self._manager.update(self, params, **kwargs)

    def _delete(self):
        """
        Delete this resource instance.
        """
        return self._manager.delete(self)

    def _action(self, action, params = None, **kwargs):
        """
        Executes the specified action on this resource instance.
        """
        return self._manager.action(self, action, params, **kwargs)


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
pprint.PrettyPrinter._dispatch[UnmanagedResource.__repr__] = pprint_resource
