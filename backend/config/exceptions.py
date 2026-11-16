from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """DRF's default handler, plus a machine-readable `code` next to every plain `detail`.

    Without this the code only exists on the Python exception object, and a client of the HTTP
    API (the React app) would have to parse English sentences to tell "slot taken" from
    "too late to cancel". Validation errors keep their per-field shape and get no `code`.
    """
    # Django's own 404/403 are converted to DRF exceptions by the default handler; do the same
    # first so they get a code as well.
    if isinstance(exc, Http404):
        exc = NotFound(*(exc.args))
    elif isinstance(exc, DjangoPermissionDenied):
        exc = PermissionDenied(*(exc.args))

    response = drf_exception_handler(exc, context)
    if (
        response is not None
        and isinstance(exc, APIException)
        and isinstance(response.data, dict)
        and "detail" in response.data
        and "code" not in response.data  # SimpleJWT already adds its own
    ):
        code = exc.get_codes()
        if isinstance(code, str):
            response.data["code"] = code
    return response
