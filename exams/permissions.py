# your_app/permissions.py

from rest_framework import permissions
from django.utils import timezone

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admins to edit objects.
    Regular users can only read.
    """
    def has_permission(self, request, view):
        # Read permissions are allowed to any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Write permissions are only allowed to admin users
        return request.user and request.user.is_staff


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to access it.
    """
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff:
            return True
        
        # Check if the object has a 'user' attribute
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        return False

# subscriptions/permissions.py


class IsSubscribed(permissions.BasePermission):
    """
    Allows access only to users with an active subscription.
    """
    message = "You do not have an active subscription. Please purchase a plan to access this content."

    def has_permission(self, request, view):
        # Ensure user is authenticated first
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check our custom property on the UserProfile
        # The related_name 'profile' from accounts/models.py is used here.
        try:
            return request.user.profile.has_active_subscription
        except AttributeError:
            # This can happen if the UserProfile signal didn't run
            return False
