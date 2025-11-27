import pytest
import app


# Helper to clear global quizzes list
@pytest.fixture(autouse=True)
def clear_quizzes():
    app.quizzes.clear()
    yield
    app.quizzes.clear()

def test_create_quiz(client):
    quiz_data = {
        "title": "Test Quiz",
        "description": "A test quiz",
        "category": "General Knowledge",
        "difficulty": "Easy",
        "time_limit": 60,
        "questions": [
            {
                "question": "What is 2+2?",
                "options": ["3", "4", "5", "6"],
                "correct": "B" # Assuming B corresponds to 2nd option '4' based on app logic usually, but app.py line 391 says correct must be A, B, C, D.
            }
        ]
    }
    response = client.post("/create-quiz", json=quiz_data)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Quiz created successfully"
    assert "quiz_id" in data
    
    # Verify it was added to the global list
    assert len(app.quizzes) == 1
    assert app.quizzes[0]["title"] == "Test Quiz"

def test_create_quiz_validation_error(client):
    quiz_data = {
        "title": "Test Quiz",
        # Missing other fields
    }
    response = client.post("/create-quiz", json=quiz_data)
    assert response.status_code == 400 # Or 422 if Pydantic validation fails before manual check, but create_quiz takes dict so manual check likely first.
    # Actually create_quiz takes dict, so it might be 422 if body is not valid json, or 400 if fields missing per manual check.
    # Looking at app.py:372 create_quiz(quiz_data: dict)
    # It manually checks fields.
    
def test_get_quizzes_db(client, db):
    # This endpoint reads from DB, so we need to insert into DB.
    # We can't use create_quiz endpoint as it writes to global list.
    from app import Quiz, Question
    
    quiz = Quiz(
        title="DB Quiz",
        category="Science",
        difficulty="Medium",
        time_limit=120
    )
    db.add(quiz)
    db.commit()
    
    response = client.get("/api/quizzes")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "DB Quiz"

def test_search_quizzes(client):
    # This endpoint reads from global list
    quiz_data = {
        "title": "Python Quiz",
        "description": "Test your python skills",
        "category": "Programming",
        "difficulty": "Hard",
        "time_limit": 300,
        "questions": [
            {
                "question": "What is PEP8?",
                "options": ["Food", "Style Guide", "Car", "Planet"],
                "correct": "B"
            }
        ]
    }
    client.post("/create-quiz", json=quiz_data)
    
    response = client.get("/search?q=python")
    assert response.status_code == 200
    data = response.json()
    assert len(data["quizzes"]) == 1
    assert data["quizzes"][0]["title"] == "Python Quiz"

    response = client.get("/search?q=java")
    assert response.status_code == 200
    data = response.json()
    assert len(data["quizzes"]) == 0

def test_submit_quiz(client):
    # Setup: Create a quiz in the global list
    quiz_data = {
        "title": "Math Quiz",
        "description": "Simple Math",
        "category": "Math",
        "difficulty": "Easy",
        "time_limit": 60,
        "questions": [
            {
                "question": "1+1?",
                "options": ["1", "2", "3", "4"],
                "correct": "B"
            },
            {
                "question": "2+2?",
                "options": ["3", "4", "5", "6"],
                "correct": "B"
            }
        ]
    }
    # We can use the create endpoint or modify list directly. Endpoint is better integration test.
    create_res = client.post("/create-quiz", json=quiz_data)
    assert create_res.status_code == 200
    quiz_id = create_res.json()["quiz_id"]

    # Submit answers
    submission_data = {
        "quiz_id": quiz_id,
        "username": "testuser",
        "answers": [
            {"question_id": 0, "answer": "B"}, # Correct
            {"question_id": 0, "answer": "A"}  # Incorrect
        ],
        "time_taken": 30
    }
    
    response = client.post("/submit-quiz", json=submission_data)
    assert response.status_code == 200
    data = response.json()
    
    assert data["score"] == 50.0
    assert data["correct"] == 1
    assert data["total"] == 2
    assert len(data["detailed_results"]) == 2
    assert data["detailed_results"][0]["is_correct"] is True
    assert data["detailed_results"][1]["is_correct"] is False
