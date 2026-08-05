from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
from typing import Optional
import os
import sqlite3
import bcrypt
import hashlib

from database import get_db

# Router
router = APIRouter(prefix="/auth", tags=["authentication"])

# OAuth2 scheme for token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# Pydantic models
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    created_at: Optional[str] = None

# Utility functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password using bcrypt"""
    # Use SHA-256 hash to handle passwords longer than 72 bytes
    password_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    return bcrypt.checkpw(password_hash.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    """Hash password using bcrypt with SHA-256 to handle longer passwords"""
    # Use SHA-256 hash to handle passwords longer than 72 bytes
    password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_hash.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        if user is None:
            raise credentials_exception
        return dict(user)

def get_current_user_optional(token: str = Depends(oauth2_scheme)):
    """Optional authentication - returns None if not authenticated"""
    try:
        return get_current_user(token)
    except HTTPException:
        return None

# Endpoints
@router.post("/register", response_model=UserResponse)
def register(user: UserRegister):
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if user already exists
        cursor.execute("SELECT * FROM users WHERE email = ?", (user.email,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create new user
        hashed_password = get_password_hash(user.password)
        cursor.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (user.email, hashed_password, user.full_name)
        )
        conn.commit()
        
        # Get the created user
        cursor.execute("SELECT * FROM users WHERE email = ?", (user.email,))
        db_user = cursor.fetchone()
        
        return {
            "id": db_user["id"],
            "email": db_user["email"],
            "full_name": db_user["full_name"],
            "created_at": db_user["created_at"]
        }

@router.post("/login", response_model=Token)
def login(user_credentials: UserLogin):
    with get_db() as conn:
        cursor = conn.cursor()
        # Find user by email
        cursor.execute("SELECT * FROM users WHERE email = ?", (user_credentials.email,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Verify password
        if not verify_password(user_credentials.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Create access token
        access_token_expires = timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        access_token = create_access_token(
            data={"sub": user["email"]}, expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user["full_name"],
                "created_at": user["created_at"]
            }
        }

@router.get("/me", response_model=UserResponse)
def get_me(current_user = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "created_at": current_user["created_at"]
    }
