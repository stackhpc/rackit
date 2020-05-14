"""
Module containing property descriptors for attaching resources in rackit.
"""

import importlib

from . import resource


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


class Endpoint(CachedProperty):
    """
    Property descriptor for attaching an unmanaged resource to a connection.
    """
    def __init__(self, resource_cls):
        self.resource_cls = resource_cls
        super().__init__(self.make_instance)

    def make_instance(self, instance):
        # Just return a lazy instance of the resource using the connection
        return self.resource_cls(instance, dict(), True)


class NestedEndpoint(Endpoint):
    """
    Property descriptor for attaching an unmanaged resource to another resource.
    """
    def get_connection(self, instance):
        if isinstance(instance, resource.Resource):
            # For managed instances, we have to go via the manager
            return instance._manager.connection
        else:
            return instance._connection

    def make_instance(self, instance):
        # Instance is a resource in this case
        # The resource path has the instance path prepended
        return self.resource_cls(
            self.get_connection(instance),
            dict(),
            True,
            "{}{}".format(
                instance._path.rstrip('/'),
                self.resource_cls._opts.endpoint
            )
        )


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

    def get_related_manager(self, instance):
        # From the instance, get a related manager for the resource class
        # This depends on whether the instance is a managed or unmanaged resource
        if isinstance(instance, resource.Resource):
            # For managed resources, use the instance's manager to get a related manager
            manager = instance._manager.related_manager(self.resource_cls)
        else:
            # For unmanaged resources, use the connection to get a root manager
            manager = instance._connection.root_manager(self.resource_cls)
        if manager:
            return manager
        else:
            raise RuntimeError('Unable to locate related manager.')

    def get_connection(self, instance):
        # From the instance, get a connection for the related instance
        if isinstance(instance, resource.Resource):
            # For managed instances, we have to go via the manager
            return instance._manager.connection
        else:
            return instance._connection

    def get_resource(self, instance):
        # If the data is empty, return now - we don't need to do anything
        data = instance[self.source_name or self.name]
        if not data:
            return None
        if issubclass(self.resource_cls, resource.Resource):
            # If the resource is managed, try to get a related manager to make the instance
            manager = self.get_related_manager(instance)
            # Return a partial resource using the embedded data
            return manager.make_instance(data, True)
        else:
            # If the resource class is an unmanaged resource, create an instance
            # directly with the connection extracted from the instance
            return self.resource_cls(
                self.get_connection(instance),
                data,
                True
            )


class EmbeddedResourceList(EmbeddedResource):
    """
    Property descriptor for an embedded list of resource instances, i.e. where a list
    of complete or partial resource instances is embedded within another resource.
    """
    def get_unmanaged_list(self, instance):
        connection = self.get_connection(instance)
        return [self.resource_cls(connection, datum, True) for datum in data]

    def get_managed_list(self, instance, data):
        manager = self.get_related_manager(instance)
        return [manager.make_instance(datum, True) for datum in data]

    def get_resource(self, instance):
        data = instance[self.source_name or self.name]
        if not data:
            return []
        if issubclass(self.resource_cls, resource.Resource):
            return self.get_managed_list(instance, data)
        else:
            return self.get_unmanaged_list(instance, data)
