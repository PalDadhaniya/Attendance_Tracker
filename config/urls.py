from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.conf.urls.static import static
from accounts.models import Employee

def custom_login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect("admin_dashboard")
        # For regular employees, check if Employee profile exists before redirecting
        try:
            employee = Employee.objects.get(user=request.user)
            if employee.is_active:
                return redirect("dashboard")
            # Employee exists but inactive - show error page
            return render(request, "employee/no_employee.html", {
                "message": "Your employee account is inactive. Please contact administrator."
            })
        except Employee.DoesNotExist:
            # Employee doesn't exist - show error page
            return render(request, "employee/no_employee.html")
    
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        
        if not username or not password:
            messages.error(request, "Please enter both Employee ID and password.")
            return render(request, "registration/login.html")
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_active:
                # Check if user is admin/staff
                if user.is_staff or user.is_superuser:
                    login(request, user)
                    messages.success(request, "Login successful!")
                    return redirect("admin_dashboard")
                # For regular employees, verify Employee profile exists BEFORE logging in
                try:
                    employee = Employee.objects.get(user=user)
                    if not employee.is_active:
                        messages.error(request, "Your employee account is inactive. Please contact administrator.")
                        return render(request, "registration/login.html")
                    # Employee exists and is active, proceed with login
                    login(request, user)
                    messages.success(request, f"Welcome, {user.get_full_name() or user.username}!")
                    return redirect("dashboard")
                except Employee.DoesNotExist:
                    messages.error(request, "Employee profile not found. Please contact administrator.")
                    return render(request, "registration/login.html")
            else:
                messages.error(request, "Your account is inactive. Please contact administrator.")
        else:
            # Check if user exists but password is wrong
            if User.objects.filter(username=username).exists():
                messages.error(request, "Invalid password.")
            else:
                messages.error(request, "Invalid Employee ID or password.")
    
    return render(request, "registration/login.html")

urlpatterns = [
    path("admin/", admin.site.urls),

    # LOGIN PAGE (ROOT URL)
    path("", custom_login_view, name="login"),

    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("", include("attendance.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)