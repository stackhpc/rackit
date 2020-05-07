"""
Module containing built-in cache implementations for rackit.
"""


class MemoryCache:
    """
    In-memory implementation for a cache of resource instances.
    """
    def __init__(self):
        # This is the instances indexed by primary key
        self.instances = {}
        # This is a mapping of alias => primary key for each alias
        self.aliases = {}

    def has(self, key):
        """
        Returns true if the key is in the cache.
        """
        # Map through aliases first
        key = self.aliases.get(key, key)
        key = str(key)
        return key in self.instances

    def get(self, key):
        """
        Returns the cache entry for the given key, or raises ``KeyError`` if none exists.
        """
        original_key = key
        # Convert the key using aliases if present
        key = self.aliases.get(key, key)
        key = str(key)
        try:
            return self.instances[key]
        except KeyError:
            # Map the key error back onto the original key
            raise KeyError(original_key)

    def put(self, resource, aliases = None):
        """
        Set a cache entry for the given resource and return it.
        """
        # The main cache key is the primary key of the resource
        key = str(resource._primary_key)
        self.instances[key] = resource
        # Set the canonical URL for the resource as an alias
        self.aliases.update({ resource._path: key })
        # If the resource has additional cache keys defined, set aliases for them
        self.aliases.update({
            (name, getattr(resource, name)): key
            for name in resource._opts.cache_keys
        })
        # Also set the given aliases
        if aliases:
            self.aliases.update({ alias: key for alias in aliases })
        return resource

    def evict(self, resource_or_key):
        """
        Evict the given resource or key from the cache. The evicted resource is returned if one exists.

        A resource can only be evicted using the primary key, not an alias.
        """
        from .resource import Resource
        if isinstance(resource_or_key, Resource):
            key = resource_or_key._primary_key
        else:
            key = resource_or_key
        return self.instances.pop(str(key), None)
