import pytest

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

REGISTER = "/api/auth/register/"
TOKEN = "/api/auth/token/"
REFRESH = "/api/auth/token/refresh/"
ME = "/api/auth/me/"


def payload(**overrides):
    data = {"email": "Alice@Example.com", "full_name": "Alice", "password": "S3cure-pass-91"}
    data.update(overrides)
    return data


def test_register_creates_client_and_normalises_email(api_client):
    response = api_client.post(REGISTER, payload(), format="json")
    assert response.status_code == 201
    assert "password" not in response.data
    user = User.objects.get(email="alice@example.com")
    assert user.role == Role.CLIENT
    assert user.check_password("S3cure-pass-91")


@pytest.mark.parametrize("role", ["admin", "provider"])
def test_register_cannot_choose_a_privileged_role(api_client, role):
    api_client.post(REGISTER, payload(role=role, is_staff=True, is_superuser=True), format="json")
    user = User.objects.get(email="alice@example.com")
    assert user.role == Role.CLIENT
    assert not user.is_staff
    assert not user.is_superuser


def test_register_rejects_weak_password(api_client):
    response = api_client.post(REGISTER, payload(password="12345678"), format="json")
    assert response.status_code == 400
    assert not User.objects.exists()


def test_register_rejects_duplicate_email_case_insensitively(api_client, make_user):
    make_user(email="alice@example.com")
    response = api_client.post(REGISTER, payload(email="ALICE@example.com"), format="json")
    assert response.status_code == 400


def test_login_returns_tokens_and_refresh_works(api_client, make_user):
    user = make_user()
    response = api_client.post(
        TOKEN, {"email": user.email, "password": "S3cure-pass-91"}, format="json"
    )
    assert response.status_code == 200
    refreshed = api_client.post(REFRESH, {"refresh": response.data["refresh"]}, format="json")
    assert refreshed.status_code == 200
    assert "access" in refreshed.data


def test_login_rejects_wrong_password(api_client, make_user):
    user = make_user()
    response = api_client.post(TOKEN, {"email": user.email, "password": "nope"}, format="json")
    assert response.status_code == 401


def test_me_requires_authentication(api_client):
    assert api_client.get(ME).status_code == 401


def test_me_returns_profile_and_ignores_role_changes(make_user, auth_client):
    user = make_user()
    client = auth_client(user)
    assert client.get(ME).data["email"] == user.email

    response = client.patch(ME, {"full_name": "New Name", "role": "admin"}, format="json")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.full_name == "New Name"
    assert user.role == Role.CLIENT
