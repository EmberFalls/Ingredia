from fastapi.testclient import TestClient

from app.main import app
from app.services.product_discovery import ProductDiscoveryService


def test_health_and_analysis() -> None:
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.json() == {"status": "ok"}
        assert health.headers["X-Request-ID"]
        assert health.headers["X-Content-Type-Options"] == "nosniff"
        response = client.post("/api/v1/analyses/text", json={"ingredient_text": "Aqua, Parfum, Mystery X", "product_category": "personal_care"})
    assert response.status_code == 201
    body = response.json()
    assert body["summary"]["unknown_ingredients"] == 1
    assert body["ingredients"][0]["canonical_name"] == "Water"
    assert body["ingredients"][1]["canonical_name"] == "Fragrance"


def test_duplicate_ingredient_does_not_inflate_product_score() -> None:
    with TestClient(app) as client:
        one = client.post("/api/v1/analyses/text", json={"ingredient_text": "Parfum", "product_category": "personal_care"}).json()
        duplicate = client.post("/api/v1/analyses/text", json={"ingredient_text": "Parfum, Fragrance", "product_category": "personal_care"}).json()
    assert one["summary"]["concern_score"] == duplicate["summary"]["concern_score"]


def test_catalog_searches_by_company_and_analyzes_product() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/products", params={"query": "Calmline"})
        assert response.status_code == 200
        products = response.json()
        assert len(products) == 3
        assert {product["brand"] for product in products} == {"Calmline"}

        analysis = client.post(f"/api/v1/products/{products[0]['id']}/analyze", json={"save_to_history": False})
    assert analysis.status_code == 201
    assert analysis.json()["summary"]["parsed_ingredients"] > 0


def test_catalog_product_detail_and_missing_product_response() -> None:
    with TestClient(app) as client:
        product = client.get("/api/v1/products", params={"query": "Calmline"}).json()[0]
        detail = client.get(f"/api/v1/products/{product['id']}")
        missing = client.get("/api/v1/products/does-not-exist")
    assert detail.status_code == 200
    assert detail.json()["ingredient_text"]
    assert detail.json()["source_name"]
    assert missing.status_code == 404


def test_catalog_data_quality_report_is_saved() -> None:
    with TestClient(app) as client:
        product = client.get("/api/v1/products", params={"barcode": "000000000001"}).json()[0]
        response = client.post(f"/api/v1/products/{product['id']}/reports", json={
            "user_id": "catalog-review-test", "reason": "outdated_label", "details": "The package label has changed.",
        })
    assert response.status_code == 201
    assert response.json()["product_id"] == product["id"]
    assert response.json()["status"] == "open"


def test_catalog_empty_barcode_and_external_unavailable_states(monkeypatch) -> None:
    with TestClient(app) as client:
        no_match = client.get("/api/v1/products", params={"barcode": "123"})
    assert no_match.status_code == 200
    assert no_match.json() == []
    assert no_match.headers["X-Catalog-Result"] == "no_match"

    async def unavailable(*_args, **_kwargs):
        return [], "external_unavailable"

    monkeypatch.setattr(ProductDiscoveryService, "search", unavailable)
    with TestClient(app) as client:
        unavailable_response = client.get("/api/v1/products", params={"query": "unavailable-product"})
    assert unavailable_response.status_code == 200
    assert unavailable_response.headers["X-Catalog-Result"] == "external_unavailable"


def test_catalog_search_supports_barcode_category_and_source_metadata() -> None:
    with TestClient(app) as client:
        barcode = client.get("/api/v1/products", params={"barcode": "000000000004"})
        category = client.get("/api/v1/products", params={"category": "food"})
        brands = client.get("/api/v1/brands", params={"query": "Northstar"})
    assert barcode.status_code == 200
    assert barcode.json()[0]["name"] == "Lemon Refresher"
    assert barcode.json()[0]["is_demo"] is True
    assert barcode.json()[0]["source_type"] == "demo"
    assert category.status_code == 200
    assert {product["category"] for product in category.json()} == {"food"}
    assert brands.status_code == 200
    assert brands.json()[0]["brand_name"] == "Northstar Pantry"


def test_profile_and_catalog_analysis_history_are_persisted() -> None:
    user_id = "profile-history-test"
    with TestClient(app) as client:
        saved = client.put(f"/api/v1/users/{user_id}/profile", json={
            "display_name": "Aaryan", "dietary_preferences": ["Vegetarian"],
            "cultural_considerations": ["Jain"], "additional_requirements": "Avoid onion and garlic.",
        })
        preference = client.put(f"/api/v1/users/{user_id}/preferences", json={"ingredient_query": "Fragrance", "preference_type": "avoid"})
        preferences = client.get(f"/api/v1/users/{user_id}/preferences")
        product = client.get("/api/v1/products", params={"barcode": "000000000002"}).json()[0]
        analyzed = client.post(f"/api/v1/products/{product['id']}/analyze", json={"user_id": user_id, "save_to_history": True})
        history = client.get(f"/api/v1/users/{user_id}/history")
    assert saved.status_code == 200
    assert saved.json()["dietary_preferences"] == ["Vegetarian"]
    assert preference.status_code == 200
    assert preferences.json()[0]["canonical_name"] == "Fragrance"
    assert analyzed.status_code == 201
    assert history.status_code == 200
    assert history.json()[0]["product_name"] == "Citrus Body Wash"
    assert history.json()[0]["product_brand"] == "Calmline"
    assert history.json()[0]["product_source_type"] == "demo"


def test_major_food_allergen_alias_matches_without_inflating_general_score() -> None:
    user_id = "food-allergen-test"
    with TestClient(app) as client:
        saved = client.put(f"/api/v1/users/{user_id}/preferences", json={"ingredient_query": "milk", "preference_type": "allergen"})
        result = client.post("/api/v1/analyses/text", json={
            "ingredient_text": "Water, Whey", "product_category": "food", "user_id": user_id,
        }).json()
    assert saved.status_code == 200
    assert result["summary"]["personal_alerts"] == 1
    assert result["summary"]["concern_score"] == 0
    assert result["ingredients"][1]["canonical_name"] == "Milk"
