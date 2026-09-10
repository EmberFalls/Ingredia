from fastapi.testclient import TestClient

from app.main import app


def test_health_and_analysis() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json() == {"status": "ok"}
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
