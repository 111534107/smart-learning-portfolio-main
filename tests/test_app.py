from app import create_app


def test_index_page_loads():
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "資管科智慧學習歷程系統".encode("utf-8") in response.data
