"""
Module containing the connection base class for rackit.
"""

import logging
import re

import requests
from requests.exceptions import RequestException, HTTPError

from .cache import MemoryCache
from .errors import ConnectionError, ApiError


class Connection:
    """
    Class for an authenticated connection.
    """
    #: The path prefix for this connection, e.g. a specific version
    #: This is added to paths that are given to the ``api_*`` methods unless
    #: they already start with it
    path_prefix = None

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

    def prepare_url(self, url):
        """
        Prepare the given URL for making a request.
        """
        # If the URL is absolute, then use it as-is
        if re.match('https?://', url) is not None:
            return url
        # Treat the url as a path now
        # If it doesn't already start with the path prefix, prepend it
        if self.path_prefix and not url.startswith(self.path_prefix):
            url = self.path_prefix + url
        # Prepend the API base URL
        return self.api_base + url

    def prepare_request(self, request):
        """
        Make any required modifications to a request before sending.

        This method is called with the prepared request.
        """
        return request

    def extract_error_message(self, response):
        """
        Extract an error message from the given error response and return it.
        """
        # By default, just use the response text
        return response.text

    def process_response(self, response):
        """
        Process the given response before returning it.

        This method should raise an error from :py:mod:`.errors` if the response is
        unsuccessful, as other parts of the code rely on a successful response.
        """
        self.log.debug("API request: \"{} {}\" {}".format(
            response.request.method,
            response.request.url,
            response.status_code
        ))
        # Convert any HTTP errors to rackit exceptions
        if response.status_code >= 400:
            raise ApiError.Code(response.status_code)(self.extract_error_message(response))
        else:
            return response

    def api_request(
        self,
        method,
        url,
        params = None,
        data = None,
        headers = None,
        cookies = None,
        files = None,
        auth = None,
        timeout = None,
        allow_redirects = True,
        proxies = None,
        hooks = None,
        stream = None,
        verify = None,
        cert = None,
        json = None
    ):
        """
        Make an API request to the given url, which may be just a path, and return the response object.

        Accepts the same parameters as the corresponding requests method.
        """
        url = self.prepare_url(url)
        request = requests.Request(
            method = method.upper(),
            url = url,
            headers = headers,
            files = files,
            data = data or {},
            json = json,
            params = params or {},
            auth = auth,
            cookies = cookies,
            hooks = hooks
        )
        # First, prepare the request using the session
        request = self.session.prepare_request(request)
        # Then apply any connection-specific changes
        request = self.prepare_request(request)
        # Calculate the send kwargs
        send_kwargs = {
            'timeout': timeout,
            'allow_redirects': allow_redirects,
        }
        send_kwargs.update(
            self.session.merge_environment_settings(
                request.url,
                proxies or {},
                stream,
                # Until https://github.com/psf/requests/issues/3829 is fixed, we must
                # specifically respect verify from the session if not specified for
                # the request in order to disregard the REQUESTS_CA_BUNDLE environment
                verify if verify is not None else self.session.verify,
                cert
            )
        )
        # Actually send the request
        try:
            response = self.session.send(request, **send_kwargs)
        except RequestException as exc:
            raise ConnectionError(str(exc)) from exc
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
