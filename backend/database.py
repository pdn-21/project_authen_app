from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

def get_url(user_key, pass_key, host_key, port_key, name_key):
    user = os.getenv(user_key)
    password = os.getenv(pass_key)
    host = os.getenv(host_key)
    port = os.getenv(port_key)
    name = os.getenv(name_key)
    
    # convert password to URL Safe
    encoded_password = quote_plus(password) if password else ""
    
    return f"mysql+pymysql://{user}:{encoded_password}@{host}:{port}/{name}"


# --- Local Database --------------------------------------------------------------------------------
# Create the database URL
SQLALCHEMY_DATABASE_URL = get_url("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")
# Create the SQLAlchemy engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- HIS Database ----------------------------------------------------------------------------------
# Create the database URL
HIS_DATABASE_URL = get_url("HIS_USER", "HIS_PASSWORD", "HIS_HOST", "HIS_PORT", "HIS_NAME")
his_engine = create_engine(HIS_DATABASE_URL)
SessionHIS = sessionmaker(autocommit=False, autoflush=False, bind=his_engine)

Base = declarative_base()

# Dependency for Local DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency for HIS DB
def get_his_db():
    his_db = SessionHIS()
    try:
        yield his_db
    finally:
        his_db.close()