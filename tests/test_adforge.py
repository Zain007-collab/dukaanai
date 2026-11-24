"""Offline tests for the AdForge bonus (no API key, no network): the model is replaced by a fake writer."""
import os
import tempfile

os.environ["DATABASE_URL"] = ""
os.environ.setdefault("LOCAL_DB", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shopbot import adforge, main  # noqa: E402
from shopbot.config import ADMIN_TOKEN  # noqa: E402

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


class FakeWriter:
    def invoke(self, _messages):
        return adforge.AdSet(audience="Women 20-35 in Islamabad and Lahore, wedding season", variants=[
            adforge.AdVariant(angle="Wedding guest glow", hook="Shaadi season ka perfect look",
                              caption="Maroon chiffon with zari work.\nOnly Rs 999 today, 50% off!",
                              hashtags=["#ShaadiSeason", "maroon suit", "#PakistaniFashion"], cta="DM us to order"),
            adforge.AdVariant(angle="Craft and fabric", hook="Hand-finished zari, made to be noticed",
                              caption="Soft chiffon that moves with you.", hashtags=["#Zari"], cta="Tap the link"),
        ])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(adforge, "build_writer", lambda: FakeWriter())
    return TestClient(main.app)


def test_clean_drops_prices_and_deals():
    assert adforge.clean("Nice suit\nOnly Rs 999 today\n50% off\nBig SALE\nDM us") == "Nice suit\nDM us"


def test_needs_admin(client):
    assert client.post("/api/admin/ads", json={"sku": "SKU-02"}).status_code == 401
    assert client.get("/api/admin/ads").status_code == 401


def test_two_variants_with_real_facts(client):
    r = client.post("/api/admin/ads", json={"sku": "sku-02", "occasion": "wedding"}, headers=ADMIN)
    assert r.status_code == 200
    out = r.json()
    assert out["sku"] == "SKU-02" and [a["variant"] for a in out["ads"]] == ["A", "B"]
    a = out["ads"][0]["text"]
    assert "Rs 999" not in a and "50%" not in a            # the model's invented deal is removed
    assert "Rs 4,800" in a                                  # the real price comes from the catalog
    assert "#maroonsuit" in a and "#ShaadiSeason" in a      # hashtags cleaned


def test_unknown_product(client):
    assert client.post("/api/admin/ads", json={"sku": "SKU-99"}, headers=ADMIN).status_code == 404


def test_click_is_counted_per_variant(client):
    ads = client.post("/api/admin/ads", json={"sku": "SKU-07"}, headers=ADMIN).json()["ads"]
    r = client.get(f"/api/ad/{ads[1]['id']}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/?ask=SKU-07")
    rows = {x["id"]: x for x in client.get("/api/admin/ads", headers=ADMIN).json()}
    assert rows[ads[1]["id"]]["clicks"] == 1 and rows[ads[0]["id"]]["clicks"] == 0
    assert client.get("/api/ad/nope", follow_redirects=False).headers["location"] == "/"


def test_chat_and_health_unaffected(client):
    assert client.get("/health").text == "ok"
