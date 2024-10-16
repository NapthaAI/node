from dotenv import load_dotenv
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Dict, List, Tuple, Optional

from node.schemas import AgentRunInput
from node.storage.db.models import User, AgentRun
from node.config import LOCAL_DB_URL
from node.utils import get_logger

logger = get_logger(__name__)

load_dotenv()

logger.info(f"Connecting to local DB: {LOCAL_DB_URL}")

engine = create_engine(LOCAL_DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class DB:
    def __init__(self):
        self.db = next(get_db())

    async def create_user(self, user_input: Dict) -> Tuple[bool, Optional[Dict]]:
        user = User(**user_input)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user.__dict__

    async def get_user(self, user_input: Dict) -> Optional[Dict]:
        user = self.db.query(User).filter_by(public_key=user_input["public_key"]).first()
        return user.__dict__ if user else None

    async def create_agent_run(self, agent_run_input: AgentRunInput) -> AgentRun:
        agent_run = AgentRun(**agent_run_input.model_dict())
        self.db.add(agent_run)
        self.db.commit()
        self.db.refresh(agent_run)
        return agent_run

    async def update_agent_run(self, agent_run_id: int, agent_run: Dict) -> bool:
        db_agent_run = self.db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
        if db_agent_run:
            for key, value in agent_run.items():
                setattr(db_agent_run, key, value)
            self.db.commit()
            return True
        return False

    async def list_agent_runs(self, agent_run_id=None) -> List[AgentRun]:
        if agent_run_id:
            return self.db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
        return self.db.query(AgentRun).all()

    async def delete_agent_run(self, agent_run_id: int) -> bool:
        agent_run = self.db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
        if agent_run:
            self.db.delete(agent_run)
            self.db.commit()
            return True
        return False

    async def query(self, query: str) -> List:
        # Raw SQL queries should be used carefully. Consider using SQLAlchemy's ORM methods instead.
        result = self.db.execute(query)
        return result.fetchall()

    async def connect(self):
        self.is_authenticated = True
        return True, None, None

    async def close(self):
        self.db.close()
        self.is_authenticated = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()