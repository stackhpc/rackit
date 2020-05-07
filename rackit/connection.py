"""
Module containing the connection base class for rackit.
"""

import logging
import re

import requests

from .cache import MemoryCache


class Connection:
    """
    Class for an authenticated connection.
    """
    def __init__(self, url, session, cache_cls = MemoryCache):
        self.session = session
        self.api_base = url.rstrip('/')
        self.cache_cls = cache_cls
        self.log = logging.getLogger(__name__)
        # The connection maintains a collection of caches, so that root resources
        # and nested resources can share a cache
        self.caches = {}
        # When a root manager is discovered, cache it
        self.root_managers = {}

    def resource_cache(self, resource_cls):
        """
        Returns this connections cache for the given resource.
        """
        if resource_cls not in self.caches:
            self.caches[resource_cls] = self.cache_cls()
        return self.caches[resource_cls]

    def root_manager(self, resource_cls):
        """
        Returns the first root manager for the given resource, or ``None`` if one
        does not exist.
        """
        from .descriptors import RootResource
        # Traverse the properties of this connection class looking for the first resource
        # manager descriptor with the correct resource class, then evaluate it for this
        # instance
        if resource_cls not in self.root_managers:
            try:
                self.root_managers[resource_cls] = next(
                    getattr(self, name)
                    for name, d in type(self).__dict__.items()
                    if isinstance(d, RootResource) and
                       issubclass(d.resource_cls, resource_cls)
                )
            except StopIteration:
                return None
        return self.root_managers[resource_cls]

    def prepare_request(self, request):
        """
        Make any required modifications to a request before sending.

        This method is called with the prepared request.
        """
        return request

    def log_request(self, request):
        """
        Make a log entry for the given request.
        """
        self.log.debug("API request: {} {}".format(request.method, request.url))

    def process_response(self, response):
        """
        Process the given response before returning it.

        This method should raise if the response is not successful, as other parts of the
        code rely on a successful response.
        """
        response.raise_for_status()
        return response

    def api_request(self, method, url, *args, **kwargs):
        """
        Make an API request to the given url, which may be just a path, and return the response object.

        Accepts the same parameters as the corresponding requests method.
        """
        # Use absolute URLs as-is, otherwise treat as a path and prepend the API base URL
        if not re.match('https?://', url):
            url = self.api_base + url
        request = requests.Request(method.upper(), url, *args, **kwargs)
        # First, prepare the request using the session
        request = self.session.prepare_request(request)
        # Then apply any connection-specific changes
        request = self.prepare_request(request)
        # Log the request before sending it
        self.log_request(request)
        response = self.session.send(request)
        # Process and return the response
        return self.process_response(response)

    def api_get(self, *args, **kwargs):
        """
        Make a GET request to the API.

        Accepts the same parameters as the corresponding requests method.
        """
        return self.api_request('get', *args, **kwargs)

    def api_post(self, *args, **kwargs):
        """
        Make a POST request to the API.

        Accepts the same parameters as the corresponding requests method.
        """
        return self.api_request('post', *args, **kwargs)

    def api_put(self, *args, **kwargs):
        """
        Make a PUT request to the API.

        Accepts the same parameters as the corresponding requests method.
        """
        return self.api_request('put', *args, **kwargs)

    def api_patch(self, *args, **kwargs):
        """
        Make a PATCH request to the API.

        Accepts the same parameters as the corresponding requests method.
        """
        return self.api_request('patch', *args, **kwargs)

    def api_delete(self, *args, **kwargs):
        """
        Make a DELETE request to the API.

        Accepts the same parameters as the corresponding requests method.
        """
        return self.api_request('delete', *args, **kwargs)

    def close(self):
        """
        Close the connection.
        """
        self.session.close()
