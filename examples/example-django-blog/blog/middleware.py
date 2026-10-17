import jwt
from django.conf import settings
from django.http import JsonResponse


class JWTAuthenticationMiddleware:
    """Middleware that decodes JWT for non-DRF views (e.g., admin)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                request.jwt_payload = payload
            except jwt.InvalidTokenError:
                pass
        return self.get_response(request)
