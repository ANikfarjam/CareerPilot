from db.models  import *

import os
from dotenv import load_dotenv

from sqlalchemy import create_engine, Select, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert

# Load environment variables from .env file
load_dotenv()

class DBConnector:
    def __init__(self):
        self.__engine = create_engine(os.getenv("DATABASE_URL"))
    
    def connect(self):
        """
            This function creates a connection and session.
            Creates the tables declared in the DB schema if they do not exist.
            @return: connection, session instances
        """
        #ensure tables are created in db
        Base.metadata.create_all(bind=self.__engine)
        connector = self.__engine.connect()
        Session = sessionmaker(bind=self.__engine)
        session = Session()
        return connector, session 
    