from django.urls import path
from .views import post_login_redirect

urlpatterns = [
    path("login-redirect/", post_login_redirect, name="login_redirect"),
]