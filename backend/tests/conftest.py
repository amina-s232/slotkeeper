import itertools

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.scheduling.models import Provider


@pytest.fixture(autouse=True)
def clear_cache():
    """DRF throttle counters live in the cache; without this they leak between tests."""
    cache.clear()


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
def make_provider(make_user):
    counter = itertools.count(1)

    def _make(**overrides):
        n = next(counter)
        user = make_user(email=f"provider{n}@example.com", role=Role.PROVIDER)
        defaults = {"display_name": f"Dr {n}", "timezone": "Asia/Kolkata"}
        defaults.update(overrides)
        return Provider.objects.create(user=user, **defaults)

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
