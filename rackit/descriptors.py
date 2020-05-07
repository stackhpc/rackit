"""
Module containing property descriptors for attaching resources in rackit.
"""

import importlib


class CachedProperty:
    """
    Property descriptor that caches the result of an expensive computed property.
    """
    def __init__(self, getter):
        self.getter = getter

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        result = instance.__dict__[self.name] = self.getter(instance)
        return result


#: Decorator that caches the result of an expensive computed property.
cached_property = CachedProperty


class ResourceManagerDescriptor(CachedProperty):
    """
    Property descriptor for attaching a resource manager to an object.
    """
    def __init__(self, resource_cls):
        self.resource_cls = resource_cls
        super().__init__(self.make_manager)

    def make_manager(self, instance):
        raise NotImplementedError


class RootResource(ResourceManagerDescriptor):
    """
    Property descriptor for attaching a root resource to a connection.
    """
    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        # When a resource is associated with a service, tell the resource
        self.resource_cls._connection_cls = owner

    def make_manager(self, instance):
        # For a root resource, the instance will be a connection
        return self.resource_cls._opts.manager_cls(
            self.resource_cls,
            instance,
            # Use the shared cache from the connection
            instance.resource_cache(self.resource_cls)
        )


class NestedResource(ResourceManagerDescriptor):
    """
    Property descriptor for attaching a nested resource to another resource.

    "Nested" means that the resource is accessed using URLs of the form
    ``/<parent_resource>/<parent id>/<child resource>[/<child id>]``. This
    library supports nesting of arbitrary depth.

    For the case where a resource or partial resource is embedded in the representation
    of another resource, use :py:class:`EmbeddedResource`.
    """
    def make_manager(self, instance):
        # For a nested resource, the instance will be an instance of the parent resource
        connection = instance._manager.connection
        return self.resource_cls._opts.manager_cls(
            self.resource_cls,
            connection,
            # Use the shared cache from the connection
            connection.resource_cache(self.resource_cls),
            # Pass the resource instance as a parent
            instance
        )


class EmbeddedResource(CachedProperty):
    """
    Property descriptor for an embedded resource instance, i.e. where a full or partial
    instance of a resource is embedded within another resource.

    In order to avoid circular dependencies where two resources reference each other,
    the resource class can be given as a string. If the string contains a dot, it is
    assumed to be of the form ``module.ClassName``. If it does not contain a dot,
    it is assumed to be ``ClassName`` and treated as relative to the containing
    resource.
    """
    def __init__(self, resource_cls, source_name = None):
        # At this point, resource_cls could be a class or a string
        # We don't want to resolve it now
        self.resource_cls = resource_cls
        self.source_name = source_name
        super().__init__(self.get_resource)

    def get_resource(self, instance):
        # If the data is empty, return None now - we don't need to do anything
        data = instance[self.source_name or self.name]
        if not data:
            return None
        # Get the related manager for the resource
        manager = instance._manager.related_manager(self.resource_cls)
        # Return a partial resource using the embedded data
        return manager.make_instance(data, True)


class EmbeddedResourceList(EmbeddedResource):
    """
    Property descriptor for an embedded list of resource instances, i.e. where a list
    of complete or partial resource instances is embedded within another resource.
    """
    def get_resource(self, instance):
        manager = instance._manager.related_manager(self.resource_cls)
        return [
            manager.make_instance(data, True)
            for data in instance[self.source_name or self.name]
        ]
