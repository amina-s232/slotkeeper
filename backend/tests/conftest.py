import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make(email="user@example.com", role=Role.CLIENT, password="S3cure-pass-91", **extra):
        return User.objects.create_user(
            email=email, password=password, full_name="Test User", role=role, **extra
        )

    return _make


@pytest.fixture
def auth_client(api_client):
    """Return an APIClient authenticated as the given user, via a real JWT login."""

    def _auth(user, password="S3cure-pass-91"):
        response = api_client.post(
            "/api/auth/token/", {"email": user.email, "password": password}, format="json"
        )
        assert response.status_code == 200, response.content
        client = type(api_client)()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client

    return _auth
