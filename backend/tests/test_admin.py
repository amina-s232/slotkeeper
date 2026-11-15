import pytest

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("model", ["provider", "availabilityrule", "timeoff", "appointment"])
def test_admin_pages_load(client, make_user, model):
    admin = make_user(email="root@example.com", role=Role.ADMIN, is_staff=True, is_superuser=True)
    client.force_login(admin)
    assert client.get(f"/django-admin/scheduling/{model}/").status_code == 200
    assert client.get(f"/django-admin/scheduling/{model}/add/").status_code == 200
