import jwt
import bcrypt
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Post, Comment
from .serializers import PostSerializer, CommentSerializer


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    email = request.POST.get("email")
    password = request.POST.get("password")
    if not email or not password:
        return JsonResponse({"error": "email and password required"}, status=400)
    from django.contrib.auth.models import User
    if User.objects.filter(email=email).exists():
        return JsonResponse({"error": "email already registered"}, status=409)
    user = User.objects.create_user(username=email, email=email, password=password)
    return JsonResponse({"id": user.id, "email": user.email}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    email = request.POST.get("email")
    password = request.POST.get("password")
    user = authenticate(request, username=email, password=password)
    if user is None:
        return JsonResponse({"error": "invalid credentials"}, status=401)
    payload = {
        "user_id": user.id,
        "email": user.email,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return JsonResponse({"token": token})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return JsonResponse({"ok": True})


class PostViewSet(viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        post = self.get_object()
        post.published = True
        post.save()
        return Response({"status": "published"})


class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated]
