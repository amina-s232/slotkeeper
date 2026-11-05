from rest_framework.permissions import BasePermission

from .models import Role


class HasRole(BasePermission):
    """Base class : subclasses set `allowed_roles`"""

    allowed_roles: tuple[str,...] = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in self.allowed_roles)


class IsAdminRole(HasRole):
    allowed_roles = (Role.ADMIN,)

class IsProviderRole(HasRole):
    allowed_roles = (Role.PROVIDER,)

class IsClientROle(HasRole):
    allowed_roles = (Role.CLIENT,)

class IsProviderOrAdmin(HasRole):
    allowed_roles = (Role.PROVIDER, Role.ADMIN)