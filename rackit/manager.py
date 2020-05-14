"""
Module containing the resource manager base class for rackit.
"""

import importlib

from .errors import NotFound


class ResourceManager:
    """
    Base class for a resource manager.
    """
    def __init__(self, resource_cls, connection, cache, parent = None):
        self.connection = connection
        self.resource_cls = resource_cls
        self.cache = cache
        self.parent = parent

    def related_resource(self, resource_cls):
        """
        Return the related resource class for the given resource class or import string.

        If an import string is given but doesn't have a module, it is treated as relative
        to ``self.resource_cls``.
        """
        # First, resolve the resource class
        if not isinstance(resource_cls, str):
            return resource_cls
        if '.' in resource_cls:
            # If there is a dot, assume it has a module
            module_name, class_name = resource_cls.rsplit('.', maxsplit = 1)
        else:
            # If not, use the module from our resource class
            module_name = self.resource_cls.__module__
            class_name = resource_cls
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def related_manager(self, resource_cls):
        """
        Return the related manager for the given resource class.

        The class can be given as a type or an import string. If the import
        string has no module, it is treated as relative to ``self.resource_cls``.
        """
        resource_cls = self.related_resource(resource_cls)
        # If the connection has a root manager for the resource, use that
        root = self.connection.root_manager(resource_cls)
        if root:
            return root
        # Otherwise, find a nested manager on a common parent
        parent = self.parent
        while parent:
            manager = parent._nested_manager(resource_cls)
            if manager:
                return manager
            else:
                parent = parent._parent

    def prepare_url(self, resource_or_key = None, action = ''):
        """
        Return the URL for the given instance.

        If no instance is given, return the base resource URL.
        """
        from .resource import Resource
        # If a resource instance is given, use the _path as the base endpoint
        if isinstance(resource_or_key, Resource):
            endpoint = resource_or_key._path
        else:
            # Otherwise, build the base endpoint
            # Start with the path of the parent resource, if present
            endpoint = self.parent._path.rstrip('/') if self.parent else ''
            # Add the endpoint from the resource class
            endpoint = endpoint + self.resource_cls._opts.endpoint
            # Append the resource key, preserving a trailing slash if present
            if resource_or_key is not None:
                endpoint = '{}/{}{}'.format(
                    endpoint.rstrip('/'),
                    resource_or_key,
                    '/' if endpoint.endswith('/') else ''
                )
        # Add the action, again preserving the trailing slash if present
        return '{}{}{}'.format(
            endpoint.rstrip('/'),
            '/' + action if action else '',
            '/' if endpoint.endswith('/') else ''
        )

    def extract_list(self, response):
        """
        Extract a list of results and a next URL from a response, as a tuple.
        """
        # Override this to extract a list from the response data
        return response.json(), None

    def extract_one(self, response):
        """
        Extract the data for a single instance from a response.
        """
        return response.json()

    def make_instance(self, data, partial = False, aliases = None):
        """
        Return a resource instance for the given data.
        """
        # If there is a root manager for the same resource, use that instead of self
        # This ensures that there is a canonical instance of each resource, even
        # if it is initially fetched as a nested resource
        manager = self.connection.root_manager(self.resource_cls) or self
        resource = self.resource_cls(manager, data, partial)
        # Don't cache partial resources
        if partial:
            return resource
        else:
            return self.cache.put(resource, aliases)

    def all(self, **params):
        """
        Return a generator of resource instances.
        """
        # This is split in case subclasses need to customise the list URL
        # on a case-by-case basis
        return self._fetch_all(self.prepare_url(), params)

    def _fetch_all(self, url, params, partial = None):
        """
        Return a generator of resource instances from the given URL.
        """
        if partial is None:
            partial = self.resource_cls._opts.list_partial
        while True:
            response = self.connection.api_get(url, params = params)
            # Extract the data and the next URL from the response
            results, url = self.extract_list(response)
            # Yield from the current page
            # We might as well make sure that we have cached everything that we have fetched
            yield from [self.make_instance(result, partial) for result in results]
            # If there is no next page, we are done
            if url is None:
                break

    def get(self, key, force = False):
        """
        Return a single resource instance by primary key.
        """
        if force:
            # If the fetch is being forced, load the resource
            return self._load(self.prepare_url(key), force)
        else:
            # If the fetch is not being forced, first try the cache
            # If the instance is not in the cache, return a lazy instance
            # that is fetched on first access for anything other than the pk
            # This allows us to avoid an unnecessary network request in the case
            # where the resource is just being used to fetch a nested resource
            # or call an action using a fluent API
            try:
                return self.cache.get(key)
            except KeyError:
                return self.make_instance(
                    { self.resource_cls._opts.primary_key_field: key },
                    partial = True
                )

    def _load(self, path, force = False):
        """
        Return a single resource instance loaded from the given path.
        """
        # This is split to allow a lazy resource to exist at a different path than the canonical path
        # The path is used as a cache alias, so check if it is present
        if not force:
            try:
                return self.cache.get(path)
            except KeyError:
                pass
        response = self.connection.api_get(path)
        # Set the actual fetched URL as a cache alias
        return self.make_instance(self.extract_one(response), aliases = (path, ))

    def find_by_ATTR(self, attr):
        """
        Returns a function that fetches one resource instance by the given attribute.
        """
        # This method is used by __getattr__ to produce the find_by_<attr>
        # methods that allow fetching a single resource instance by an attribute
        # value
        def find_by_attr(manager, value, as_params = True, force = False):
            # First, try to find the resource in the cache
            if not force:
                try:
                    return manager.cache.get((attr, value))
                except KeyError:
                    pass
            # Use the attribute value as parameters for the fetch if requested
            params = { attr: value } if as_params else {}
            try:
                result = next(
                    resource
                    for resource in manager.all(**params)
                    if getattr(resource, attr) == value
                )
            except StopIteration:
                return None
            else:
                # Cache the result with the attribute value of the alias
                return self.cache.put(result, aliases = [(attr, value)])
        return lambda *args, **kwargs: find_by_attr(self, *args, **kwargs)

    def __getattr__(self, name):
        if not name.startswith("find_by_"):
            message = "'{}' object has no attribute '{}'".format(
                self.__class__.__name__,
                name
            )
            raise AttributeError(message)
        return self.find_by_ATTR(name[8:])

    def prepare_params(self, params):
        """
        Prepare the parameters by de-referencing any aliases.
        """
        return {
            self.resource_cls._opts.aliases.get(k, k): v
            for k, v in params.items()
        }

    def create(self, params = None, **kwargs):
        """
        Create a new resource instance with the given parameters.
        """
        # Combine the params and kwargs to get the parameters
        params = params.copy() if params else dict()
        params.update(kwargs)
        params = self.prepare_params(params)
        response = self.connection.api_post(self.prepare_url(), json = params)
        # Return a lazy instance, in case the whole resource is not known
        return self.make_instance(self.extract_one(response), True)

    def update(self, resource_or_key, params = None, **kwargs):
        """
        Update the given resource instance or key with the given parameters.
        """
        # Combine the params and kwargs to get the parameters
        params = params.copy() if params else dict()
        params.update(kwargs)
        params = self.prepare_params(params)
        endpoint = self.prepare_url(resource_or_key)
        # Decide which verb to use to update the resource
        verb = self.resource_cls._opts.update_http_verb.lower()
        method = getattr(self.connection, 'api_{}'.format(verb))
        response = method(endpoint, json = params)
        return self.make_instance(self.extract_one(response))

    def delete(self, resource_or_key):
        """
        Delete the given resource instance or key.
        """
        self.connection.api_delete(self.prepare_url(resource_or_key))
        self.cache.evict(resource_or_key)

    def action(self, resource_or_key, action, params = None, **kwargs):
        """
        Execute an action on the given resource or key with the given params.
        """
        params = params.copy() if params else dict()
        params.update(kwargs)
        endpoint = self.prepare_url(resource_or_key, action)
        self.connection.api_post(endpoint, json = params)
        # When the action is successful, evict the resource from the cache
        # This type of endpoint is not restful, so cannot be relied upon to
        # return a resource instance in the response
        self.cache.evict(resource_or_key)
