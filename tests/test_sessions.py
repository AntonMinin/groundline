import jwt

from app.config import settings
from tests.conftest import auth_headers


async def test_logout_revokes_the_token_it_was_sent_with(client, make_user):
    user = await make_user()
    headers = auth_headers(user.id)
    assert (await client.get("/me", headers=headers)).status_code == 200
    assert (await client.post("/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/me", headers=headers)).status_code == 401


async def test_logout_ends_every_session_of_the_account(client, make_user):
    user, other = await make_user(), await make_user()
    laptop, phone = auth_headers(user.id), auth_headers(user.id)
    await client.post("/auth/logout", headers=laptop)
    assert (await client.get("/me", headers=phone)).status_code == 401
    assert (await client.get("/me", headers=auth_headers(user.id, version=1))).status_code == 200
    assert (await client.get("/me", headers=auth_headers(other.id))).status_code == 200


async def test_a_token_from_before_versions_existed_works_until_the_first_logout(client, make_user):
    user = await make_user()
    legacy = jwt.encode({"sub": str(user.id), "exp": 4_102_444_800}, settings.jwt_secret, algorithm="HS256")
    headers = {"Cookie": f"{settings.cookie_name}={legacy}"}
    assert (await client.get("/me", headers=headers)).status_code == 200
    await client.post("/auth/logout", headers=headers)
    assert (await client.get("/me", headers=headers)).status_code == 401


async def test_a_revoked_or_forged_cookie_on_logout_changes_nothing(client, make_user):
    user = await make_user()
    fresh = auth_headers(user.id)
    await client.post("/auth/logout", headers={"Cookie": f"{settings.cookie_name}=not-a-token"})
    await client.post("/auth/logout", headers=auth_headers(user.id, version=5))
    assert (await client.get("/me", headers=fresh)).status_code == 200


async def test_logout_without_a_cookie_still_clears_it(client):
    response = await client.post("/auth/logout")
    assert response.status_code == 204
    assert settings.cookie_name in response.headers.get("set-cookie", "")
