import pytest

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db


def test_create_user_defaults_to_client_and_hashes_password():
    user = User.objects.creat_user("A@Example.com", "S3cure-pass-91", full_name="A")
    assert user.email == "a@example.com"
    assert user.role == Role.CLIENT
    assert user.password != "S3cure-pass-91"
    assert not user.is_staff


def test_create_superuser_is_admin_and_staff():
    user = User.objects.create_superuser("root@example.com", "S3cure-pass-91", full_name="R")
    assert user.role == Role.ADMIN
    assert user.is_staff and user.is_superuser
