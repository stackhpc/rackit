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


def resolve_python_object(import_string, relative_to):
    """
    Resolve the given import string.

    The import string is assumed to be of the form ``[module.]objectname``. If it does not
    have a module it is resolved relative to the given object.
    """
    if '.' in import_string:
        # If there is a dot, assume it has a module
        module_name, object_name = import_string.rsplit('.', maxsplit = 1)
    else:
        # If not, use the module from relative_to
        module_name, object_name = relative_to.__module__, import_string
    module = importlib.import_module(module_name)
    return getattr(module, object_name)


class ResourceClassDescriptor(CachedProperty):
    """
    Base class for property descriptors that require a resource class.

    Allows the resource class to be either a string or a Python object in order to support
    circular references.
    """
    def __init__(self, resource_cls, getter):
        self._resource_cls = resource_cls
        super().__init__(getter)

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        # Store the owner so that we can use it later to resolve the resource cls
        self.owner = owner

    @cached_property
    def resource_cls(self):
        if isinstance(self._resource_cls, str):
            return resolve_python_object(self._resource_cls, self.owner)
        else:
            return self._resource_cls


class Endpoint(ResourceClassDescriptor):
    """
    Property descriptor for attaching an unmanaged resource to a connection.
    """
    def __init__(self, resource_cls):
        super().__init__(resource_cls, self.make_instance)

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


class ResourceManagerDescriptor(ResourceClassDescriptor):
    """
    Property descriptor for attaching a resource manager to an object.
    """
    def __init__(self, resource_cls):
        super().__init__(resource_cls, self.make_manager)

    def make_manager(self, instance):
        raise NotImplementedError


class RootResource(ResourceManagerDescriptor):
    """
    Property descriptor for attaching a root resource to a connection.
    """
    @cached_property
    def resource_cls(self):
        # When the resource class is resolved, set it's connection class
        resource_cls = super().resource_cls
        resource_cls._connection_cls = self.owner
        return resource_cls

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


class RelatedResource(ResourceClassDescriptor):
    """
    Property descriptor for a related resource instance, i.e. where an id of a related
    resource is included within another resource.
    """
    def __init__(self, resource_cls, source_field = None):
        self.source_field = source_field
        super().__init__(resource_cls, self.get_resource)

    def get_data(self, instance):
        # From the instance, get the data to use for the related resource
        # By default, assume it is a primary key
        pk_field = self.resource_cls._opts.primary_key_field
        try:
            return { pk_field: instance[self.source_field or self.name] }
        except KeyError:
            return None

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
        print(self)
        print(instance)
        data = self.get_data(instance)
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


class EmbeddedResource(RelatedResource):
    """
    Property descriptor for an embedded resource instance, i.e. where a full or partial
    instance of a resource is embedded within another resource.
    """
    def get_data(self, instance):
        try:
            return instance[self.source_field or self.name]
        except KeyError:
            return None


class RelatedResourceList(RelatedResource):
    """
    Property descriptor for an embedded list of related resources, i.e. where a list of
    related ids is included within another resource.
    """
    def get_data(self, instance):
        # Get the primary key field for the related model
        pk_field = self.resource_cls._opts.primary_key_field
        try:
            return [
                { pk_field: pk }
                for pk in instance[self.source_field or self.name]
            ]
        except KeyError:
            return []

    def get_unmanaged_list(self, instance, data):
        connection = self.get_connection(instance)
        return [self.resource_cls(connection, datum, True) for datum in data]

    def get_managed_list(self, instance, data):
        manager = self.get_related_manager(instance)
        return [manager.make_instance(datum, True) for datum in data]

    def get_resource(self, instance):
        data = self.get_data(instance)
        if not data:
            return []
        if issubclass(self.resource_cls, resource.Resource):
            return self.get_managed_list(instance, data)
        else:
            return self.get_unmanaged_list(instance, data)


class EmbeddedResourceList(RelatedResourceList):
    """
    Property descriptor for an embedded list of resource instances, i.e. where a list
    of complete or partial resource instances is embedded within another resource.
    """
    def get_data(self, instance):
        try:
            return instance[self.source_field or self.name]
        except KeyError:
            return []
