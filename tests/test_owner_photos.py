"""Tests for POST /owner/listings/{id}/photos (real file upload).

Storage root is redirected per-test via RESTAMP_MEDIA_ROOT (read per-call
by app/services/storage.py), so no test files ever touch real storage and
tmp dirs vanish with the test. DB rows roll back via the shared fixture.
"""
import base64
import io

import pytest
from sqlalchemy import text
from tests.conftest import auth_header, register_phone

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
JPEG_BYTES = b"\xff\xd8\xff\xe0FAKEJPEG" + b"0" * 128


def _setup_owner(c, phone: str) -> str:
    token = register_phone(c, phone)["access_token"]
    r = c.post("/users/me/role", json={"role": "OWNER"}, headers=auth_header(token))
    assert r.status_code == 200, r.text
    return token


def _create_listing(c, token: str, title: str, **extra) -> int:
    payload = {
        "title": title, "transaction_type": "RENT", "property_type": "APARTMENT",
        "price_rupees": 25000, "price_period": "MONTHLY",
        "locality": "Photo Nagar", "city": "Chennai", "pincode": "600090",
        **extra,
    }
    r = c.post("/owner/listings", json=payload, headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()["listing_id"]


def _upload(c, token, listing_id, content: bytes, filename: str, mime: str, category="Living Room"):
    return c.post(
        f"/owner/listings/{listing_id}/photos",
        files={"file": (filename, io.BytesIO(content), mime)},
        data={"category": category},
        headers=auth_header(token),
    )


def test_upload_succeeds_and_persists_all_metadata(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, session = client
    token = _setup_owner(c, "+919876543301")
    lid = _create_listing(c, token, "Photo Full Flat")
    r = _upload(c, token, lid, PNG_1PX, "a.png", "image/png", "Bedroom")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["category"] == "Bedroom"
    assert body["mime_type"] == "image/png"
    assert body["byte_size"] == len(PNG_1PX)
    assert body["order_index"] == 0 and body["is_cover"] is True
    assert body["url"].startswith("http") and body["url"].endswith(".png")
    row = session.execute(text(
        "SELECT url, category, mime_type, byte_size, order_index, media_type, uploaded_by "
        "FROM property_media WHERE property_listing_id=:i"), {"i": lid}).fetchone()
    assert tuple(row) == (body["url"], "Bedroom", "image/png", len(PNG_1PX), 0, "IMAGE",
                          session.execute(text(
                              "SELECT user_id FROM property_listings WHERE id=:i"),
                              {"i": lid}).fetchone()[0])
    # File on disk with the stored bytes.
    from app.services import storage as storage_svc
    assert storage_svc.stored_file_path("/".join(body["url"].rsplit("/", 2)[-2:])).read_bytes() == PNG_1PX


def test_first_photo_is_cover_second_is_not(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, session = client
    token = _setup_owner(c, "+919876543302")
    lid = _create_listing(c, token, "Photo Order Flat")
    first = _upload(c, token, lid, PNG_1PX, "a.png", "image/png", "Living Room").json()
    second = _upload(c, token, lid, JPEG_BYTES, "b.jpg", "image/jpeg", "Kitchen").json()
    assert (first["order_index"], first["is_cover"]) == (0, True)
    assert (second["order_index"], second["is_cover"]) == (1, False)
    detail = c.get(f"/owner/listings/{lid}", headers=auth_header(token)).json()
    assert detail["cover_image_url"] == first["url"]
    assert [p["url"] for p in detail["photos"]] == [first["url"], second["url"]]


def test_upload_appends_after_existing_url_media(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, session = client
    token = _setup_owner(c, "+919876543303")
    lid = _create_listing(c, token, "Photo Append Flat",
                          images=["https://t.test/cover.jpg"])
    body = _upload(c, token, lid, PNG_1PX, "a.png", "image/png", "Balcony").json()
    assert (body["order_index"], body["is_cover"]) == (1, False)
    detail = c.get(f"/owner/listings/{lid}", headers=auth_header(token)).json()
    assert detail["cover_image_url"] == "https://t.test/cover.jpg"


def test_unsupported_mime_rejected(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, _ = client
    token = _setup_owner(c, "+919876543304")
    lid = _create_listing(c, token, "Photo Mime Flat")
    r = _upload(c, token, lid, b"GIF89a", "a.gif", "image/gif")
    assert r.status_code == 422, r.text


def test_mismatched_extension_rejected(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, _ = client
    token = _setup_owner(c, "+919876543305")
    lid = _create_listing(c, token, "Photo Ext Flat")
    r = _upload(c, token, lid, PNG_1PX, "evil.exe", "image/png")
    assert r.status_code == 422, r.text
    r = _upload(c, token, lid, PNG_1PX, "a.png", "image/jpeg")
    assert r.status_code == 422, r.text


def test_oversized_file_rejected(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, _ = client
    token = _setup_owner(c, "+919876543306")
    lid = _create_listing(c, token, "Photo Big Flat")
    r = _upload(c, token, lid, b"0" * (10 * 1024 * 1024 + 1), "big.jpg", "image/jpeg")
    assert r.status_code == 422, r.text


def test_empty_file_rejected(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, _ = client
    token = _setup_owner(c, "+919876543307")
    lid = _create_listing(c, token, "Photo Empty Flat")
    r = _upload(c, token, lid, b"", "empty.jpg", "image/jpeg")
    assert r.status_code == 422, r.text


def test_invalid_category_rejected(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, _ = client
    token = _setup_owner(c, "+919876543308")
    lid = _create_listing(c, token, "Photo Cat Flat")
    r = _upload(c, token, lid, PNG_1PX, "a.png", "image/png", "Sauna")
    assert r.status_code == 422, r.text


def test_unauthenticated_is_401(client):
    c, _ = client
    r = c.post("/owner/listings/1/photos",
               files={"file": ("a.png", io.BytesIO(PNG_1PX), "image/png")},
               data={"category": "Living Room"})
    assert r.status_code == 401, r.text


def test_buyer_is_403(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, _ = client
    buyer_token = register_phone(c, "+919876543309")["access_token"]
    owner_token = _setup_owner(c, "+919876543310")
    lid = _create_listing(c, owner_token, "Photo Buyer Flat")
    r = _upload(c, buyer_token, lid, PNG_1PX, "a.png", "image/png")
    assert r.status_code == 403, r.text


def test_cross_owner_is_404_and_stores_nothing(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, session = client
    token_a = _setup_owner(c, "+919876543311")
    token_b = _setup_owner(c, "+919876543312")
    lid = _create_listing(c, token_a, "Photo Private Flat")
    before = session.execute(text("SELECT COUNT(*) FROM property_media")).fetchone()[0]
    r = _upload(c, token_b, lid, PNG_1PX, "a.png", "image/png")
    assert r.status_code == 404, r.text
    after = session.execute(text("SELECT COUNT(*) FROM property_media")).fetchone()[0]
    assert after == before
    from app.services import storage as storage_svc
    leftovers = [p for p in storage_svc.ensure_media_root().rglob("*") if p.is_file()]
    assert leftovers == []


def test_db_failure_removes_orphan_file(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, session = client
    token = _setup_owner(c, "+919876543313")
    lid = _create_listing(c, token, "Photo Orphan Flat")
    before = session.execute(text("SELECT COUNT(*) FROM property_media")).fetchone()[0]
    from app.services import owner_listings as svc
    monkeypatch.setattr(svc, "add_listing_photo",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = _upload(c, token, lid, PNG_1PX, "a.png", "image/png")
    assert r.status_code == 500, r.text
    from app.services import storage as storage_svc
    leftovers = [p for p in storage_svc.ensure_media_root().rglob("*") if p.is_file()]
    assert leftovers == []


def test_storage_failure_creates_no_row(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, session = client
    token = _setup_owner(c, "+919876543314")
    lid = _create_listing(c, token, "Photo StoreFail Flat")
    before = session.execute(text(
        "SELECT COUNT(*) FROM property_media WHERE property_listing_id=:i"),
        {"i": lid}).fetchone()[0]
    from app.services import storage as storage_svc
    monkeypatch.setattr(storage_svc, "save_listing_image",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk gone")))
    r = _upload(c, token, lid, PNG_1PX, "a.png", "image/png")
    assert r.status_code == 500, r.text
    after = session.execute(text(
        "SELECT COUNT(*) FROM property_media WHERE property_listing_id=:i"),
        {"i": lid}).fetchone()[0]
    assert after == before


def test_existing_listing_data_intact(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    c, session = client
    token = _setup_owner(c, "+919876543315")
    lid = _create_listing(c, token, "Photo Intact Flat",
                          description="Keep me",
                          rent_terms={"lock_in_months": 12},
                          amenities=["Gym"])
    _upload(c, token, lid, PNG_1PX, "a.png", "image/png", "Exterior")
    card = c.get(f"/owner/listings/{lid}", headers=auth_header(token)).json()
    assert card["description"] == "Keep me"
    assert card["rent_terms"]["lock_in_months"] == 12
    assert card["amenities"] == ["Gym"]
    assert card["verification_status"] == "PENDING"


def test_served_over_http_with_fresh_app(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAMP_MEDIA_ROOT", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import db as db_module
    from app.main import create_app
    c, session = client

    def _override():
        try:
            yield session
        finally:
            pass

    app2 = create_app()
    app2.dependency_overrides[db_module.get_db] = _override
    with TestClient(app2) as t:
        token = register_phone(t, "+919876543316")["access_token"]
        t.post("/users/me/role", json={"role": "OWNER"}, headers=auth_header(token))
        lid = t.post("/owner/listings", json={
            "title": "Photo Serve Flat", "price_rupees": 100,
            "locality": "L", "city": "C", "pincode": "600316"},
            headers=auth_header(token)).json()["listing_id"]
        up = t.post(f"/owner/listings/{lid}/photos",
                    files={"file": ("a.png", io.BytesIO(PNG_1PX), "image/png")},
                    data={"category": "Exterior"},
                    headers=auth_header(token))
        assert up.status_code == 201, up.text
        url = up.json()["url"]
        path = url.split("/media/", 1)[1]
        r = t.get(f"/media/{path}")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"
        assert r.content == PNG_1PX
