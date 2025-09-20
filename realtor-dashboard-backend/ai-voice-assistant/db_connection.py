import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import threading
import time

class DatabasePool:
    _instance = None
    _lock = threading.Lock()
    _pool = None
    _connection_string = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabasePool, cls).__new__(cls)
        return cls._instance

    def set_connection_string(self, connection_string):
        # Set the database connection string directly
        self._connection_string = connection_string
        print(f"Database connection string set from external source")
        return self

    def initialize(self, min_connections=2, max_connections=10):
        # Initialize the connection pool
        if self._pool is None:
            try:
                # First try to use the connection string provided by Node.js
                if self._connection_string:
                    connection_string = self._connection_string
                else:
                    # Fall back to environment variable if not provided by Node.js
                    connection_string = os.getenv('DATABASE_URL')
                    if not connection_string:
                        raise ValueError("DATABASE_URL environment variable is not set")
                
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=min_connections,
                    maxconn=max_connections,
                    dsn=connection_string
                )
                print(f"Database pool initialized with {min_connections}-{max_connections} connections")
            except Exception as e:
                print(f"Error initializing database pool: {e}")
                raise
    def check_connection_health(self):
        # Verify pool connections are healthy and reconnect if needed
        if not self._pool:
            print("Database pool not initialized, attempting to reconnect")
            self.initialize()
            return False
            
        try:
            # Test a connection from the pool
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result is not None
        except Exception as e:
            print(f"Database connection health check failed: {e}")
            # Close the pool and reinitialize it
            self.close()
            self._pool = None
            self.initialize()
            return False

    @contextmanager
    def get_connection(self):
        # Get a connection from the pool
        conn = None
        retry_attempts = 3
        retry_delay = 1  # seconds
        
        for attempt in range(retry_attempts):
            try:
                conn = self._pool.getconn()
                
                # Test if connection is still valid
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                
                yield conn
                break
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                if conn:
                    self._pool.putconn(conn, close=True)  # Close this bad connection
                    conn = None
                
                if attempt < retry_attempts - 1:
                    print(f"Database connection failed, retrying in {retry_delay}s... ({attempt+1}/{retry_attempts})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print("Max retry attempts reached. Database connection failed.")
                    raise
            finally:
                if conn:
                    self._pool.putconn(conn)

    @contextmanager
    def get_cursor(self, cursor_factory=RealDictCursor):
        # Get a cursor using a pooled connection
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

    def close(self):
        # Close all pooled connections
        if self._pool:
            self._pool.closeall()
            print("Closed all database connections")

def get_db():
    # Get database pool instance
    return DatabasePool()

def initialize_db(pool_config=None, connection_string=None):
    # Initialize the database pool with optional configuration
    if pool_config is None:
        pool_config = {
            'min_connections': 2,
            'max_connections': 10
        }
    
    try:
        db_pool = DatabasePool()
        
        # Set connection string if provided
        if connection_string:
            db_pool.set_connection_string(connection_string)
            
        db_pool.initialize(
            min_connections=pool_config.get('min_connections', 2),
            max_connections=pool_config.get('max_connections', 10)
        )
        
        print("Database connection pool initialized successfully")
        return db_pool, db_pool  # Return pool instance twice for backward compatibility
    except Exception as e:
        print(f"Error initializing database pool: {e}")
        raise