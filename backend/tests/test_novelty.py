from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_resolution_trace_coverage_and_neutral_uncertainty() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/analyses/text", json={
            "ingredient_text": "Aqua, Parfum, Parfom, HydraComplex-Z",
            "product_category": "personal_care",
        })
    assert response.status_code == 201
    body = response.json()
    aqua, parfum, uncertain, unknown = body["ingredients"]
    assert aqua["canonical_name"] == "Water"
    assert aqua["match"]["method"] == "exact_alias"
    assert aqua["match"]["status"] == "resolved"
    assert parfum["canonical_name"] == "Fragrance"
    assert uncertain["match"]["status"] == "uncertain"
    assert uncertain["concern_score"] == 0
    assert uncertain["product_contribution"] == 0
    assert unknown["match"]["status"] == "unknown"
    assert unknown["concern_score"] == 0
    assert body["summary"]["resolved_ingredients"] == 2
    assert body["summary"]["uncertain_ingredients"] == 1
    assert body["summary"]["unknown_ingredients"] == 1
    assert body["summary"]["coverage"] == 0.5


def test_preferences_do_not_change_general_score() -> None:
    with TestClient(app) as client:
        user_with_preference = f"personal-{uuid4()}"
        user_without_preference = f"general-{uuid4()}"
        client.put(f"/api/v1/users/{user_with_preference}/preferences", json={
            "ingredient_query": "Fragrance", "preference_type": "sensitivity",
        })
        first = client.post("/api/v1/analyses/text", json={
            "ingredient_text": "Aqua, Parfum, Limonene",
            "product_category": "personal_care", "user_id": user_with_preference,
        }).json()
        second = client.post("/api/v1/analyses/text", json={
            "ingredient_text": "Aqua, Parfum, Limonene",
            "product_category": "personal_care", "user_id": user_without_preference,
        }).json()
    assert first["summary"]["concern_score"] == second["summary"]["concern_score"]
    assert first["summary"]["personal_alerts"] == 1
    assert second["summary"]["personal_alerts"] == 0


def test_verified_family_membership_is_data_driven() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/analyses/text", json={
            "ingredient_text": "PTFE, Fluorinated-looking mystery",
        }).json()
    assert response["ingredients"][0]["families"][0]["slug"] == "pfas-related"
    assert response["ingredients"][0]["families"][0]["source_url"].startswith("https://www.oecd.org/")
    assert response["ingredients"][1]["families"] == []


def test_score_contributors_are_traceable_to_evidence() -> None:
    with TestClient(app) as client:
        body = client.post("/api/v1/analyses/text", json={
            "ingredient_text": "Parfum, Limonene",
            "product_category": "personal_care",
        }).json()
    contributors = body["score_breakdown"]["top_contributors"]
    assert contributors
    assert all(item["evidence_record_ids"] for item in contributors)
    assert all(reason["source_url"] for item in contributors for reason in item["reasons"])
    assert round(sum(item["contribution"] for item in contributors)) == body["summary"]["concern_score"]


def test_repeated_encounters_count_once_per_saved_analysis() -> None:
    user_id = f"encounters-{uuid4()}"
    with TestClient(app) as client:
        for label in ("Parfum, Fragrance, Aqua", "Parfum, Limonene"):
            client.post("/api/v1/analyses/text", json={
                "ingredient_text": label, "product_name": "Encounter product",
                "product_category": "personal_care", "user_id": user_id,
                "save_to_history": True,
            })
        insights = client.get(f"/api/v1/users/{user_id}/insights/ingredients", params={"days": 7})
    assert insights.status_code == 200
    body = insights.json()
    fragrance = next(item for item in body["ingredients"] if item["canonical_name"] == "Fragrance")
    assert body["total_analyses"] == 2
    assert fragrance["product_encounters"] == 2
    assert "do not represent absorbed dose" in body["disclaimer"]


def test_comparison_reasons_and_catalog_provenance_are_exposed() -> None:
    with TestClient(app) as client:
        comparison = client.post("/api/v1/comparisons", json={
            "product_a": {"ingredient_text": "Aqua, Parfum, Limonene", "product_category": "personal_care"},
            "product_b": {"ingredient_text": "Aqua, Glycerin", "product_category": "personal_care"},
        }).json()
        product = client.get("/api/v1/products", params={"limit": 1}).json()[0]
        analysis = client.post(f"/api/v1/products/{product['id']}/analyze", json={"save_to_history": False}).json()
    assert comparison["score_delta"] > 0
    assert comparison["main_reasons"]
    assert comparison["main_reasons"][0]["contribution_delta"] > 0
    assert analysis["provenance"]["input_type"] == "catalog"
    assert analysis["provenance"]["source_url"] == product["source_url"]


def test_complete_logged_in_novelty_journey() -> None:
    email = f"novelty-{uuid4()}@example.com"
    label = "Aqua, Glycerin, Parfum, Limonene, HydraComplex-Z"
    with TestClient(app) as client:
        auth = client.post("/api/v1/auth/register", json={
            "email": email, "password": "novelty-test-42", "display_name": "Novelty Test",
        }).json()
        user_id = auth["account"]["id"]
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        preference = client.put(
            f"/api/v1/users/{user_id}/preferences",
            headers=headers,
            json={"ingredient_query": "Fragrance", "preference_type": "sensitivity"},
        )
        first = client.post("/api/v1/analyses/text", headers=headers, json={
            "ingredient_text": label, "product_name": "Five ingredient scenario",
            "product_category": "personal_care", "user_id": user_id, "save_to_history": True,
        }).json()
        client.post("/api/v1/analyses/text", headers=headers, json={
            "ingredient_text": "Aqua, Parfum", "product_name": "Second scenario",
            "product_category": "personal_care", "user_id": user_id, "save_to_history": True,
        })
        insights = client.get(
            f"/api/v1/users/{user_id}/insights/ingredients", headers=headers, params={"days": 30},
        ).json()
        comparison = client.post("/api/v1/comparisons", headers=headers, json={
            "product_a": {"ingredient_text": label, "product_category": "personal_care", "user_id": user_id},
            "product_b": {"ingredient_text": "Aqua, Glycerin", "product_category": "personal_care", "user_id": user_id},
        }).json()
    assert preference.status_code == 200
    assert first["summary"]["coverage"] == 0.8
    assert first["summary"]["personal_alerts"] == 1
    assert first["ingredients"][2]["personal_alert"]["canonical_name"] == "Fragrance"
    assert first["ingredients"][4]["match"]["status"] == "unknown"
    assert first["score_breakdown"]["top_contributors"]
    fragrance = next(item for item in insights["ingredients"] if item["canonical_name"] == "Fragrance")
    assert fragrance["product_encounters"] == 2
    assert comparison["main_reasons"]
