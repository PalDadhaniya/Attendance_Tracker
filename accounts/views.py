from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

@login_required
def post_login_redirect(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect("admin_dashboard")

    return redirect("dashboard")