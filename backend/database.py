import sqlite3
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional
import json
from contextlib import contextmanager

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_PATH = "./deploycheck.db"

# Determine if using PostgreSQL or SQLite
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.strip())

def get_db_connection():
    """Get a database connection"""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
    else:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
    return conn

class CompatibleCursor:
    """Wrapper around database cursor to handle SQLite vs PostgreSQL placeholder and dict row differences"""
    def __init__(self, conn):
        self.conn = conn
        if USE_POSTGRES:
            self.cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            self.cursor = conn.cursor()
    
    def execute(self, query: str, params=()):
        if USE_POSTGRES:
            query = query.replace('?', '%s')
        return self.cursor.execute(query, params)
    
    def fetchone(self):
        return self.cursor.fetchone()
    
    def fetchall(self):
        return self.cursor.fetchall()
    
    @property
    def lastrowid(self):
        if USE_POSTGRES:
            return getattr(self.cursor, 'lastrowid', None)
        return self.cursor.lastrowid
    
    def __getattr__(self, name):
        return getattr(self.cursor, name)

class CompatibleConnection:
    """Wrapper around connection to return CompatibleCursor"""
    def __init__(self, conn):
        self._conn = conn
    
    def cursor(self):
        return CompatibleCursor(self._conn)
    
    def commit(self):
        return self._conn.commit()
    
    def rollback(self):
        return self._conn.rollback()
    
    def close(self):
        return self._conn.close()

def init_db():
    """Initialize the database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    if USE_POSTGRES:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    # Create analyses table
    if USE_POSTGRES:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                critical_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                passed_count INTEGER DEFAULT 0,
                total_files INTEGER DEFAULT 0,
                issues_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                critical_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                passed_count INTEGER DEFAULT 0,
                total_files INTEGER DEFAULT 0,
                issues_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
    
    conn.commit()
    conn.close()

@contextmanager
def get_db():
    """Context manager for database operations"""
    raw_conn = get_db_connection()
    conn = CompatibleConnection(raw_conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
