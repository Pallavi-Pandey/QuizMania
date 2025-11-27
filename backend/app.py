import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel

from config import settings

# --- Database Setup ---
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Pydantic Schemas (Data Validation) ---
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserPublic(BaseModel):
    id: int
    username: str
    total_score: int
    quizzes_taken: int

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class QuestionPublic(BaseModel):
    id: int
    question_text: str
    question_type: str
    options: Optional[List[str]]
    points: int

    class Config:
        orm_mode = True

class QuizPublic(BaseModel):
    id: int
    title: str
    description: Optional[str]
    category: str
    difficulty: str
    time_limit: int
    question_count: int

    class Config:
        orm_mode = True

class QuizDetail(QuizPublic):
    questions: List[QuestionPublic]

class Answer(BaseModel):
    question_id: int
    answer: str

class QuizSubmission(BaseModel):
    quiz_id: int
    username: str
    answers: List[Answer]
    time_taken: int

class QuizResultPublic(BaseModel):
    score: int
    total_questions: int
    percentage: float
    time_taken: int

# --- SQLAlchemy Models (Database Tables) ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_score = Column(Integer, default=0)
    quizzes_taken = Column(Integer, default=0)

class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    category = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)
    time_limit = Column(Integer, default=300)
    created_at = Column(DateTime, default=datetime.utcnow)
    questions = relationship('Question', back_populates='quiz', cascade='all, delete-orphan')

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey('quizzes.id'), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String, nullable=False)
    options = Column(Text)
    correct_answer = Column(String, nullable=False)
    points = Column(Integer, default=1)
    order = Column(Integer, default=0)
    quiz = relationship('Quiz', back_populates='questions')

class QuizResult(Base):
    __tablename__ = "quiz_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    quiz_id = Column(Integer, ForeignKey('quizzes.id'), nullable=False)
    score = Column(Integer, nullable=False)
    total_questions = Column(Integer, nullable=False)
    time_taken = Column(Integer)
    completed_at = Column(DateTime, default=datetime.utcnow)
    answers = Column(Text)

# --- FastAPI App Initialization ---
app = FastAPI()

# Add CORS middleware to allow frontend access
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependency Injection ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Authentication ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# --- Global Data Storage (minimal for compatibility) ---
quizzes = []
quiz_history = []
quiz_collaborators = []
collaboration_invitations = []

# --- API Endpoints ---
def initialize_sample_data():
    """Initialize minimal quiz data for compatibility"""
    global quizzes
    quizzes = []

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    # Initialize sample quiz data for compatibility
    initialize_sample_data()


@app.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    
    db_user = User(username=user.username, email=user.email, password=user.password) # In production, hash this!
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not user.password == form_data.password: # In production, use proper password hashing
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/quizzes", response_model=List[QuizPublic])
def get_quizzes(category: Optional[str] = None, difficulty: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Quiz)
    if category:
        query = query.filter(Quiz.category == category)
    if difficulty:
        query = query.filter(Quiz.difficulty == difficulty)
    quizzes = query.all()
    return [{**quiz.__dict__, "question_count": len(quiz.questions)} for quiz in quizzes]

@app.get("/quizzes")
def get_all_quizzes(db: Session = Depends(get_db)):
    """Get all quizzes from database"""
    quizzes = db.query(Quiz).all()
    quiz_list = []
    for quiz in quizzes:
        quiz_dict = {
            "id": quiz.id,
            "title": quiz.title,
            "description": quiz.description,
            "category": quiz.category,
            "difficulty": quiz.difficulty,
            "time_limit": quiz.time_limit,
            "question_count": len(quiz.questions)
        }
        quiz_list.append(quiz_dict)
    return {"quizzes": quiz_list}

@app.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    """Get leaderboard data from quiz results"""
    # Get all quiz results and calculate stats per user
    from sqlalchemy import func
    
    leaderboard_query = db.query(
        func.coalesce(User.username, 'Anonymous').label('username'),
        func.sum(QuizResult.score).label('total_score'),
        func.count(QuizResult.id).label('quizzes_taken'),
        func.avg(QuizResult.score).label('average_score')
    ).join(User, QuizResult.user_id == User.id).group_by(User.username).order_by(func.sum(QuizResult.score).desc()).all()
    
    leaderboard = []
    for entry in leaderboard_query:
        leaderboard.append({
            "username": entry.username,
            "total_score": int(entry.total_score or 0),
            "quizzes_taken": entry.quizzes_taken,
            "average_score": round(float(entry.average_score or 0), 1)
        })
    
    # If no data, return sample data for demo
    if not leaderboard:
        leaderboard = [
            {"username": "admin", "total_score": 100, "quizzes_taken": 5, "average_score": 85.0},
            {"username": "user1", "total_score": 80, "quizzes_taken": 4, "average_score": 80.0},
            {"username": "user2", "total_score": 60, "quizzes_taken": 3, "average_score": 75.0}
        ]
    
    return {"leaderboard": leaderboard}

@app.get("/api/quizzes/{quiz_id}", response_model=QuizDetail)
def get_quiz(quiz_id: int, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # Manually process questions to fit the Pydantic model
    questions_public = []
    for q in sorted(quiz.questions, key=lambda x: x.order):
        questions_public.append(
            QuestionPublic(
                id=q.id,
                question_text=q.question_text,
                question_type=q.question_type,
                options=json.loads(q.options) if q.options else None,
                points=q.points
            )
        )

    return QuizDetail(
        id=quiz.id,
        title=quiz.title,
        description=quiz.description,
        category=quiz.category,
        difficulty=quiz.difficulty,
        time_limit=quiz.time_limit,
        question_count=len(quiz.questions),
        questions=questions_public
    )

@app.post("/submit-quiz")
async def submit_quiz(submission: QuizSubmission):
    # Calculate score
    quiz = next((q for q in quizzes if q["id"] == submission.quiz_id), None)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    correct_answers = 0
    total_questions = len(quiz["questions"])
    detailed_results = []
    
    for i, answer in enumerate(submission.answers):
        question = quiz["questions"][i]
        is_correct = answer.answer == question["correct"]
        if is_correct:
            correct_answers += 1
        
        detailed_results.append({
            "question": question["question"],
            "your_answer": answer,
            "correct_answer": question["correct"],
            "is_correct": is_correct,
            "options": question["options"]
        })
    
    score = (correct_answers / total_questions) * 100
    
    # Add to leaderboard
    leaderboard = []  
    quiz_history = []  # Store user quiz attempts with detailed results
    leaderboard_entry = {
        "username": submission.username,
        "quiz_title": quiz["title"],
        "score": score,
        "date": datetime.now().isoformat()
    }
    leaderboard.append(leaderboard_entry)
    quiz_history.append({
        "username": submission.username,
        "quiz_title": quiz["title"],
        "score": score,
        "date": datetime.now().isoformat(),
        "detailed_results": detailed_results
    })
    
    return {
        "score": score, 
        "correct": correct_answers, 
        "total": total_questions,
        "detailed_results": detailed_results
    }

@app.post("/create-quiz")
async def create_quiz(quiz_data: dict):
    # Generate new quiz ID
    new_id = max([q["id"] for q in quizzes]) + 1 if quizzes else 1
    
    # Validate quiz data
    required_fields = ["title", "description", "category", "difficulty", "time_limit", "questions"]
    for field in required_fields:
        if field not in quiz_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    # Validate questions
    if len(quiz_data["questions"]) < 1:
        raise HTTPException(status_code=400, detail="Quiz must have at least 1 question")
    
    for i, question in enumerate(quiz_data["questions"]):
        if not all(key in question for key in ["question", "options", "correct"]):
            raise HTTPException(status_code=400, detail=f"Question {i+1} is missing required fields")
        if len(question["options"]) < 2:
            raise HTTPException(status_code=400, detail=f"Question {i+1} must have at least 2 options")
        if question["correct"] not in ["A", "B", "C", "D"]:
            raise HTTPException(status_code=400, detail=f"Question {i+1} correct answer must be A, B, C, or D")
    
    new_quiz = {
        "id": new_id,
        "title": quiz_data["title"],
        "description": quiz_data["description"],
        "category": quiz_data["category"],
        "difficulty": quiz_data["difficulty"],
        "time_limit": quiz_data["time_limit"],
        "questions": quiz_data["questions"],
        "created_by": quiz_data.get("created_by", "Anonymous"),
        "created_date": datetime.now().isoformat(),
        "attempts": 0,
        "average_score": 0
    }
    
    quizzes.append(new_quiz)
    return {"message": "Quiz created successfully", "quiz_id": new_id}

@app.get("/categories")
async def get_categories():
    categories = list(set([quiz["category"] for quiz in quizzes]))
    return {"categories": categories}

@app.get("/quizzes/category/{category}")
async def get_quizzes_by_category(category: str):
    filtered_quizzes = [quiz for quiz in quizzes if quiz["category"].lower() == category.lower()]
    return {"quizzes": filtered_quizzes}

@app.get("/search")
async def search_quizzes(q: str = ""):
    if not q:
        return {"quizzes": quizzes}
    
    search_term = q.lower()
    filtered_quizzes = [
        quiz for quiz in quizzes 
        if search_term in quiz["title"].lower() or 
           search_term in quiz["description"].lower() or 
           search_term in quiz["category"].lower()
    ]
    return {"quizzes": filtered_quizzes}

@app.post("/quiz-history")
def submit_quiz_result(quiz_data: dict, db: Session = Depends(get_db)):
    """Submit quiz result to database"""
    try:
        # Create a new quiz result entry
        quiz_result = QuizResult(
            user_id=1,  # Default user for demo
            quiz_id=1,  # We'll need to map from quiz_title to quiz_id later
            score=quiz_data.get('score', 0),
            total_questions=quiz_data.get('total_questions', 0),
            time_taken=quiz_data.get('time_taken', 0),
            answers=json.dumps(quiz_data.get('answers', {}))
        )
        
        db.add(quiz_result)
        db.commit()
        db.refresh(quiz_result)
        
        return {"message": "Quiz result submitted successfully", "id": quiz_result.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit quiz result: {str(e)}")

@app.get("/quiz-history/{username}")
async def get_quiz_history(username: str):
    user_history = [entry for entry in quiz_history if entry["username"] == username]
    return {"history": user_history}

@app.get("/user-stats/{username}")
async def get_user_stats(username: str):
    user_attempts = [entry for entry in quiz_history if entry["username"] == username]
    
    if not user_attempts:
        return {
            "quizzesCompleted": 0,
            "averageScore": 0,
            "perfectScores": 0,
            "fastestTime": 0,
            "categoriesExplored": 0,
            "quizzesCreated": 0
        }
    
    total_score = sum(attempt["score"] for attempt in user_attempts)
    average_score = total_score / len(user_attempts)
    perfect_scores = len([attempt for attempt in user_attempts if attempt["score"] == 100])
    
    # Get unique categories from user's quiz attempts
    categories_explored = len(set([
        next(q["category"] for q in quizzes if q["title"] == attempt["quiz_title"])
        for attempt in user_attempts
    ]))
    
    # Count quizzes created by user
    quizzes_created = len([q for q in quizzes if q.get("created_by") == username])
    
    return {
        "quizzesCompleted": len(user_attempts),
        "averageScore": round(average_score, 1),
        "perfectScores": perfect_scores,
        "fastestTime": 95,  # Mock data for now
        "categoriesExplored": categories_explored,
        "quizzesCreated": quizzes_created
    }


@app.get("/quiz-analytics/{quiz_id}")
async def get_quiz_analytics(quiz_id: int):
    # Get quiz details
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # Get quiz attempts from history
    attempts = [h for h in quiz_history if h.get("quiz_id") == quiz_id or h["quiz_title"] == quiz["title"]]
    
    if not attempts:
        return {
            "quiz": quiz,
            "total_attempts": 0,
            "average_score": 0,
            "completion_rate": 0,
            "score_distribution": [],
            "attempts_over_time": [],
            "question_analytics": []
        }
    
    # Calculate analytics
    total_attempts = len(attempts)
    average_score = sum(a["score"] for a in attempts) / total_attempts
    
    # Score distribution
    score_ranges = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
    for attempt in attempts:
        score = attempt["score"]
        if score <= 25:
            score_ranges["0-25"] += 1
        elif score <= 50:
            score_ranges["26-50"] += 1
        elif score <= 75:
            score_ranges["51-75"] += 1
        else:
            score_ranges["76-100"] += 1
    
    # Attempts over time (group by date)
    from collections import defaultdict
    attempts_by_date = defaultdict(int)
    for attempt in attempts:
        date = attempt["date"][:10]  # Get date part only
        attempts_by_date[date] += 1
    
    attempts_over_time = [{"date": date, "count": count} for date, count in attempts_by_date.items()]
    
    # Question analytics
    question_analytics = []
    if attempts and "detailed_results" in attempts[0]:
        for i, question in enumerate(quiz["questions"]):
            correct_count = 0
            total_count = 0
            for attempt in attempts:
                if "detailed_results" in attempt and i < len(attempt["detailed_results"]):
                    total_count += 1
                    if attempt["detailed_results"][i]["is_correct"]:
                        correct_count += 1
            
            question_analytics.append({
                "question": question["question"],
                "correct_rate": (correct_count / total_count * 100) if total_count > 0 else 0,
                "total_attempts": total_count
            })
    
    return {
        "quiz": quiz,
        "total_attempts": total_attempts,
        "average_score": round(average_score, 1),
        "completion_rate": 100,  # Assuming all started quizzes are completed
        "score_distribution": [{"range": k, "count": v} for k, v in score_ranges.items()],
        "attempts_over_time": sorted(attempts_over_time, key=lambda x: x["date"]),
        "question_analytics": question_analytics
    }

@app.get("/creator-analytics/{username}")
async def get_creator_analytics(username: str):
    # Get quizzes created by this user (mock data for now)
    user_quizzes = [q for q in quizzes if q.get("created_by") == username]
    
    # Get all attempts for user's quizzes
    total_attempts = 0
    total_score = 0
    attempt_count = 0
    
    quiz_performance = []
    for quiz in user_quizzes:
        attempts = [h for h in quiz_history if h["quiz_title"] == quiz["title"]]
        quiz_attempts = len(attempts)
        total_attempts += quiz_attempts
        
        if attempts:
            avg_score = sum(a["score"] for a in attempts) / len(attempts)
            total_score += sum(a["score"] for a in attempts)
            attempt_count += len(attempts)
        else:
            avg_score = 0
        
        quiz_performance.append({
            "quiz_id": quiz["id"],
            "quiz_title": quiz["title"],
            "attempts": quiz_attempts,
            "average_score": round(avg_score, 1),
            "category": quiz["category"],
            "difficulty": quiz["difficulty"]
        })
    
    overall_avg_score = (total_score / attempt_count) if attempt_count > 0 else 0
    
    return {
        "total_quizzes": len(user_quizzes),
        "total_attempts": total_attempts,
        "overall_average_score": round(overall_avg_score, 1),
        "quiz_performance": quiz_performance,
        "categories": list(set(q["category"] for q in user_quizzes)),
        "difficulties": list(set(q["difficulty"] for q in user_quizzes))
    }

@app.get("/recommendations/{username}")
async def get_quiz_recommendations(username: str):
    # Simple recommendation - just return available quizzes
    return {
        "recommendations": quizzes[:6],
        "total_recommendations": min(6, len(quizzes))
    }

@app.get("/export-quiz/{quiz_id}")
async def export_quiz(quiz_id: int):
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # Get quiz statistics for export
    quiz_attempts = [h for h in quiz_history if h["quiz_title"] == quiz["title"]]
    quiz_ratings = [r for r in quiz_ratings_data if r["quiz_id"] == quiz_id]
    
    export_data = {
        "quiz_data": {
            **quiz,
            "export_date": datetime.now().isoformat(),
            "export_version": "1.0"
        },
        "statistics": {
            "total_attempts": len(quiz_attempts),
            "average_score": sum(a["score"] for a in quiz_attempts) / len(quiz_attempts) if quiz_attempts else 0,
            "total_ratings": len(quiz_ratings),
            "average_rating": sum(r["rating"] for r in quiz_ratings) / len(quiz_ratings) if quiz_ratings else 0
        },
        "metadata": {
            "exported_by": "QuizMaster",
            "format_version": "1.0",
            "compatible_versions": ["1.0"]
        }
    }
    
    return export_data

class QuizImport(BaseModel):
    quiz_data: dict
    import_options: dict = {}

@app.post("/import-quiz")
async def import_quiz(import_data: QuizImport):
    try:
        quiz_data = import_data.quiz_data
        
        # Validate required fields
        required_fields = ["title", "description", "category", "difficulty", "time_limit", "questions"]
        for field in required_fields:
            if field not in quiz_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Validate questions format
        if not isinstance(quiz_data["questions"], list) or len(quiz_data["questions"]) == 0:
            raise HTTPException(status_code=400, detail="Quiz must have at least one question")
        
        for i, question in enumerate(quiz_data["questions"]):
            required_q_fields = ["question", "options", "correct"]
            for field in required_q_fields:
                if field not in question:
                    raise HTTPException(status_code=400, detail=f"Question {i+1} missing field: {field}")
            
            if not isinstance(question["options"], list) or len(question["options"]) < 2:
                raise HTTPException(status_code=400, detail=f"Question {i+1} must have at least 2 options")
        
        # Create new quiz with new ID
        new_quiz = {
            "id": len(quizzes) + 1,
            "title": quiz_data["title"],
            "description": quiz_data["description"],
            "category": quiz_data["category"],
            "difficulty": quiz_data["difficulty"],
            "time_limit": quiz_data["time_limit"],
            "questions": quiz_data["questions"],
            "question_count": len(quiz_data["questions"]),
            "created_by": import_data.import_options.get("created_by", "Imported"),
            "created_date": datetime.now().isoformat(),
            "imported": True,
            "original_export_date": quiz_data.get("export_date"),
            "ratings": [],
            "average_rating": 0
        }
        
        # Add to quizzes list
        quizzes.append(new_quiz)
        
        return {
            "message": "Quiz imported successfully",
            "quiz_id": new_quiz["id"],
            "quiz_title": new_quiz["title"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")

@app.get("/export-multiple-quizzes")
async def export_multiple_quizzes(quiz_ids: str = ""):
    if not quiz_ids:
        raise HTTPException(status_code=400, detail="No quiz IDs provided")
    
    try:
        quiz_id_list = [int(id.strip()) for id in quiz_ids.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid quiz ID format")
    
    exported_quizzes = []
    for quiz_id in quiz_id_list:
        quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
        if quiz:
            quiz_attempts = [h for h in quiz_history if h["quiz_title"] == quiz["title"]]
            quiz_ratings = [r for r in quiz_ratings_data if r["quiz_id"] == quiz_id]
            
            exported_quizzes.append({
                "quiz_data": {
                    **quiz,
                    "export_date": datetime.now().isoformat(),
                    "export_version": "1.0"
                },
                "statistics": {
                    "total_attempts": len(quiz_attempts),
                    "average_score": sum(a["score"] for a in quiz_attempts) / len(quiz_attempts) if quiz_attempts else 0,
                    "total_ratings": len(quiz_ratings),
                    "average_rating": sum(r["rating"] for r in quiz_ratings) / len(quiz_ratings) if quiz_ratings else 0
                }
            })
    
    export_package = {
        "quizzes": exported_quizzes,
        "export_metadata": {
            "total_quizzes": len(exported_quizzes),
            "export_date": datetime.now().isoformat(),
            "exported_by": "QuizMaster",
            "format_version": "1.0",
            "package_type": "multiple_quizzes"
        }
    }
    
    return export_package

# Quiz collaboration data structures
quiz_collaborators = []  # [{quiz_id, username, role, status, invited_by, invited_at}]
collaboration_invitations = []  # [{id, quiz_id, inviter, invitee, role, status, created_at}]

# Quiz collaboration endpoints
@app.post("/quiz-collaboration/invite")
async def invite_collaborator(invitation: dict):
    """Invite a user to collaborate on a quiz"""
    quiz_id = invitation.get("quiz_id")
    inviter = invitation.get("inviter")
    invitee = invitation.get("invitee")
    role = invitation.get("role", "editor")  # editor, reviewer, viewer
    
    # Check if quiz exists
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # Check if inviter is the owner or has admin rights
    if quiz["creator"] != inviter:
        existing_collab = next((c for c in quiz_collaborators 
                               if c["quiz_id"] == quiz_id and c["username"] == inviter 
                               and c["role"] in ["admin", "owner"]), None)
        if not existing_collab:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Check if already invited or collaborating
    existing_invitation = next((i for i in collaboration_invitations 
                               if i["quiz_id"] == quiz_id and i["invitee"] == invitee 
                               and i["status"] == "pending"), None)
    if existing_invitation:
        raise HTTPException(status_code=400, detail="User already invited")
    
    existing_collaborator = next((c for c in quiz_collaborators 
                                 if c["quiz_id"] == quiz_id and c["username"] == invitee), None)
    if existing_collaborator:
        raise HTTPException(status_code=400, detail="User already collaborating")
    
    # Create invitation
    invitation_id = len(collaboration_invitations) + 1
    new_invitation = {
        "id": invitation_id,
        "quiz_id": quiz_id,
        "inviter": inviter,
        "invitee": invitee,
        "role": role,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "quiz_title": quiz["title"]
    }
    
    collaboration_invitations.append(new_invitation)
    return {"message": "Invitation sent successfully", "invitation_id": invitation_id}

@app.get("/quiz-collaboration/invitations/{username}")
async def get_user_invitations(username: str):
    """Get all pending invitations for a user"""
    user_invitations = [
        inv for inv in collaboration_invitations 
        if inv["invitee"] == username and inv["status"] == "pending"
    ]
    return {"invitations": user_invitations}

@app.post("/quiz-collaboration/respond-invitation")
async def respond_to_invitation(response: dict):
    """Accept or decline a collaboration invitation"""
    invitation_id = response.get("invitation_id")
    action = response.get("action")  # "accept" or "decline"
    username = response.get("username")
    
    # Find invitation
    invitation = next((i for i in collaboration_invitations if i["id"] == invitation_id), None)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    if invitation["invitee"] != username:
        raise HTTPException(status_code=403, detail="Not authorized to respond to this invitation")
    
    if invitation["status"] != "pending":
        raise HTTPException(status_code=400, detail="Invitation already responded to")
    
    # Update invitation status
    invitation["status"] = "accepted" if action == "accept" else "declined"
    invitation["responded_at"] = datetime.now().isoformat()
    
    # If accepted, add to collaborators
    if action == "accept":
        collaborator = {
            "quiz_id": invitation["quiz_id"],
            "username": username,
            "role": invitation["role"],
            "status": "active",
            "invited_by": invitation["inviter"],
            "invited_at": invitation["created_at"],
            "joined_at": datetime.now().isoformat()
        }
        quiz_collaborators.append(collaborator)
        return {"message": "Invitation accepted", "collaborator": collaborator}
    else:
        return {"message": "Invitation declined"}

@app.get("/quiz-collaboration/{quiz_id}/collaborators")
async def get_quiz_collaborators(quiz_id: int):
    """Get all collaborators for a quiz"""
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    collaborators = [c for c in quiz_collaborators if c["quiz_id"] == quiz_id and c["status"] == "active"]
    
    # Include quiz owner
    owner = {
        "quiz_id": quiz_id,
        "username": quiz["creator"],
        "role": "owner",
        "status": "active",
        "joined_at": quiz.get("created_at", datetime.now().isoformat())
    }
    
    return {"collaborators": [owner] + collaborators}

@app.delete("/quiz-collaboration/{quiz_id}/collaborators/{username}")
async def remove_collaborator(quiz_id: int, username: str, remover: dict):
    """Remove a collaborator from a quiz"""
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    remover_username = remover.get("username")
    
    # Check permissions - only owner or admin can remove collaborators
    if quiz["creator"] != remover_username:
        remover_collab = next((c for c in quiz_collaborators 
                              if c["quiz_id"] == quiz_id and c["username"] == remover_username 
                              and c["role"] == "admin"), None)
        if not remover_collab:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Cannot remove the owner
    if username == quiz["creator"]:
        raise HTTPException(status_code=400, detail="Cannot remove quiz owner")
    
    # Find and remove collaborator
    collaborator = next((c for c in quiz_collaborators 
                        if c["quiz_id"] == quiz_id and c["username"] == username), None)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    
    quiz_collaborators.remove(collaborator)
    return {"message": "Collaborator removed successfully"}

@app.get("/quiz-collaboration/user/{username}/quizzes")
async def get_user_collaborative_quizzes(username: str):
    """Get all quizzes a user is collaborating on"""
    user_collaborations = [c for c in quiz_collaborators 
                          if c["username"] == username and c["status"] == "active"]
    
    collaborative_quizzes = []
    for collab in user_collaborations:
        quiz = next((q for q in quizzes if q["id"] == collab["quiz_id"]), None)
        if quiz:
            quiz_info = {
                **quiz,
                "collaboration_role": collab["role"],
                "joined_at": collab["joined_at"]
            }
            collaborative_quizzes.append(quiz_info)
    
    return {"collaborative_quizzes": collaborative_quizzes}
