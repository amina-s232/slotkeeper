from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import Role, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "role"]
        read_only_fields = ["id", "email", "role"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "password"]
        read_only_fields = ["id"]

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        # Validate against a transient user so UserAttributeSimilarityValidator can work.
        candidate = User(email=attrs["email"], full_name=attrs["full_name"])
        password_validation.validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        # `role` is never read from request data: self-registration always makes a client.
        return User.objects.create_user(role=Role.CLIENT, **validated_data)
