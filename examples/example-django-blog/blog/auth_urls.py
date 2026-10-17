from django.urls import path
from blog import views

urlpatterns = [
    path("register", views.register, name="auth-register"),
    path("login", views.login_view, name="auth-login"),
    path("logout", views.logout_view, name="auth-logout"),
]
