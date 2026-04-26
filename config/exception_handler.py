"""
Custom exception handler for Django REST Framework.

Ensures ALL API errors are returned as JSON — never HTML.
This prevents the "Unexpected token '<'" error in the frontend
when Django returns an HTML 404/500 page in production (DEBUG=False).
"""

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotAuthenticated,
    PermissionDenied,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Wrap the default DRF handler so every error — including Django's
    built-in Http404 and unexpected 500s — returns a JSON body.
    """
    # Let DRF handle its own exceptions first
    response = exception_handler(exc, context)

    if response is not None:
        # Normalise the body to always have an "error" key
        if isinstance(response.data, dict) and "detail" in response.data:
            response.data = {"error": str(response.data["detail"])}
        return response

    # ----- Fallback for exceptions DRF doesn't catch -----

    # Django's Http404 (raised by get_object_or_404 outside DRF views)
    if isinstance(exc, Http404):
        return Response(
            {"error": "Not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Anything else is an unexpected server error — log it and return 500 JSON
    import logging
    logger = logging.getLogger("django.request")
    logger.error("Unhandled API exception: %s", exc, exc_info=True)

    return Response(
        {"error": "Internal server error."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
