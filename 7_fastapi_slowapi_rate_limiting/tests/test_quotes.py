class TestListQuotes:
    def test_returns_all_public_quotes(self, client):
        response = client.get("/api/v1/quotes/")
        assert response.status_code == 200
        data = response.json()
        assert "quotes" in data
        assert len(data["quotes"]) == 8
        assert all(not q["is_premium"] for q in data["quotes"])

    def test_quote_has_expected_fields(self, client):
        response = client.get("/api/v1/quotes/")
        data = response.json()
        quote = data["quotes"][0]
        assert "id" in quote
        assert "text" in quote
        assert "author" in quote
        assert "category" in quote
        assert "is_premium" in quote


class TestRandomQuote:
    def test_returns_a_quote(self, client):
        response = client.get("/api/v1/quotes/random")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "text" in data
        assert not data["is_premium"]


class TestGetQuoteById:
    def test_returns_existing_quote(self, client):
        response = client.get(
            "/api/v1/quotes/1",
            headers={"X-API-Key": "free_test_key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["text"] == "The only limit to our realization of tomorrow is our doubts of today."

    def test_returns_404_for_missing_quote(self, client):
        response = client.get(
            "/api/v1/quotes/999",
            headers={"X-API-Key": "free_test_key"},
        )
        assert response.status_code == 404

    def test_returns_premium_quote_by_id(self, client):
        response = client.get(
            "/api/v1/quotes/9",
            headers={"X-API-Key": "free_test_key"},
        )
        assert response.status_code == 200
        assert response.json()["is_premium"] is True


class TestPremiumQuotes:
    def test_returns_premium_quotes(self, client):
        response = client.get(
            "/api/v1/quotes/premium",
            headers={"X-API-Key": "free_test_key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "quotes" in data
        assert len(data["quotes"]) == 4
        assert all(q["is_premium"] for q in data["quotes"])