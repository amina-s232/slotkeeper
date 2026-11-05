
from rest_framework import generics, permissions

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class MeView(generics.RetrieveUpdateAPIView):
    """Current user's own profile .  role and email cannot be changed here."""

    serializer_class =UserSerializer
    http_method_names = ["get","patch","head","options"]

    def get_object(self):
        return self.request.user
    