from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect

def logout_view(request):
    """Vue personnalisée pour la déconnexion"""
    auth_views.LogoutView.as_view()(request)
    return redirect('login')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('newsletters.urls')),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', logout_view, name='logout'),
] 