"""
Module providing exceptions for rackit.
"""


class RackitError(RuntimeError):
    """
    Base class for all Rackit errors.
    """


class ConnectionError(RackitError):
    """
    Raised when there is a problem with a connection.

    Will always be raised with the requests exception as the cause.
    """


class ApiError(RackitError):
    """
    Raised when there is an HTTP error interacting with an API.

    Will always be raised with the requests exception as the cause.
    """
    _registry = dict()

    status_code = 500
    status_text = "Internal Server Error"

    def __repr__(self):
        return "{} {}: {}".format(self.status_code, self.status_text, str(self))

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # When a subclass is created, store it in the registry indexed by status code
        # This allows us to get the class by status code later
        cls._registry[cls.status_code] = cls

    @classmethod
    def Code(cls, status_code):
        """
        Returns the exception class for the given status code.
        """
        try:
            # Try to fetch the exception class from the registry
            return cls._registry[status_code]
        except KeyError:
            # If there is no exception class for the status code, make one
            cls._registry[status_code] = error_cls = type(
                'ApiError{}'.format(status_code),
                (ApiError, ),
                dict(status_code = status_code, status_text = "Unknown")
            )
            return error_cls


class BadRequest(ApiError):
    status_code = 400
    status_text = "Bad Request"


class Unauthorized(ApiError):
    status_code = 401
    status_text = "Unauthorized"


class PaymentRequired(ApiError):
    status_code = 402
    status_text = "Payment Required"

class Forbidden(ApiError):
    status_code = 403
    status_text = "Forbidden"


class NotFound(ApiError):
    status_code = 404
    status_text = "Not Found"


class MethodNotAllowed(ApiError):
    status_code = 405
    status_text = "Method Not Allowed"


class NotAcceptable(ApiError):
    status_code = 406
    status_text = "Not Acceptable"


class ProxyAuthenticationRequired(ApiError):
    status_code = 407
    status_text = "Proxy Authentication Required"


class RequestTimeout(ApiError):
    status_code = 408
    status_text = "Request Timeout"


class Conflict(ApiError):
    status_code = 409
    status_text = "Conflict"


class Gone(ApiError):
    status_code = 410
    status_text = "Gone"


class LengthRequired(ApiError):
    status_code = 411
    status_text = "Length Required"


class PreconditionFailed(ApiError):
    status_code = 412
    status_text = "Precondition Failed"


class PayloadTooLarge(ApiError):
    status_code = 413
    status_text = "Payload Too Large"


class URITooLong(ApiError):
    status_code = 414
    status_text = "URI Too Long"


class UnsupportedMediaType(ApiError):
    status_code = 415
    status_text = "Unsupported Media Type"


class RangeNotSatisfiable(ApiError):
    status_code = 416
    status_text = "Range Not Satisfiable"


class ExpectationFailed(ApiError):
    status_code = 417
    status_text = "Expectation Failed"


class ImATeapot(ApiError):
    status_code = 418
    status_text = "I'm a teapot"


class MisdirectedRequest(ApiError):
    status_code = 421
    status_text = "Misdirected Request"


class UnprocessableEntity(ApiError):
    status_code = 422
    status_text = "Unprocessable Entity"


class Locked(ApiError):
    status_code = 423
    status_text = "Locked"


class FailedDependency(ApiError):
    status_code = 424
    status_text = "Failed Dependency"


class TooEarly(ApiError):
    status_code = 425
    status_text = "Too Early"


class UpgradeRequired(ApiError):
    status_code = 426
    status_text = "Upgrade Required"


class PreconditionRequired(ApiError):
    status_code = 428
    status_text = "Precondition Required"


class TooManyRequests(ApiError):
    status_code = 429
    status_text = "Too Many Requests"


class RequestHeaderFieldsTooLarge(ApiError):
    status_code = 431
    status_text = "Request Header Fields Too Large"


class UnavailableForLegalReasons(ApiError):
    status_code = 451
    status_text = "Unavailable For Legal Reasons"


class InternalServerError(ApiError):
    status_code = 500
    status_text = "Internal Server Error"


class NotImplemented(ApiError):
    status_code = 501
    status_text = "Not Implemented"


class BadGateway(ApiError):
    status_code = 502
    status_text = "Bad Gateway"


class ServiceUnavailable(ApiError):
    status_code = 503
    status_text = "Service Unavailable"


class GatewayTimeout(ApiError):
    status_code = 504
    status_text = "Gateway Timeout"


class HTTPVersionNotSupported(ApiError):
    status_code = 505
    status_text = "HTTP Version Not Supported"


class VariantAlsoNegotiates(ApiError):
    status_code = 506
    status_text = "Variant Also Negotiates"


class InsufficientStorage(ApiError):
    status_code = 507
    status_text = "Insufficient Storage"


class LoopDetected(ApiError):
    status_code = 508
    status_text = "Loop Detected"


class NotExtended(ApiError):
    status_code = 510
    status_text = "Not Extended"


class NetworkAuthenticationRequired(ApiError):
    status_code = 511
    status_text = "Network Authentication Required"
