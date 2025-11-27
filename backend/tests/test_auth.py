from app import User

def test_register_user(client, db):
    response = client.post(
        "/register",
        json={"username": "testuser", "email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verify user in DB
    user = db.query(User).filter(User.username == "testuser").first()
    assert user is not None
    assert user.email == "test@example.com"

def test_register_duplicate_username(client):
    # First registration
    client.post(
        "/register",
        json={"username": "testuser", "email": "test@example.com", "password": "password123"},
    )
    # Duplicate registration
    response = client.post(
        "/register",
        json={"username": "testuser", "email": "other@example.com", "password": "password123"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already exists"

def test_register_duplicate_email(client):
    # First registration
    client.post(
        "/register",
        json={"username": "testuser", "email": "test@example.com", "password": "password123"},
    )
    # Duplicate email
    response = client.post(
        "/register",
        json={"username": "otheruser", "email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already exists"

def test_login_success(client):
    # Register first
    client.post(
        "/register",
        json={"username": "testuser", "email": "test@example.com", "password": "password123"},
    )
    # Login
    response = client.post(
        "/token",
        data={"username": "testuser", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid_credentials(client):
    # Register first
    client.post(
        "/register",
        json={"username": "testuser", "email": "test@example.com", "password": "password123"},
    )
    # Login with wrong password
    response = client.post(
        "/token",
        data={"username": "testuser", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"
