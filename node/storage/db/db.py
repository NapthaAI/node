import logging
from contextlib import contextmanager
from typing import Dict, List, Tuple, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from node.schemas import AgentRunInput
from node.storage.db.models import User, AgentRun
from node.config import LOCAL_DB_URL
from node.schemas import AgentRun as AgentRunSchema

logger = logging.getLogger(__name__)

engine = create_engine(
    LOCAL_DB_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class DB:
    def __init__(self):
        self.is_authenticated = False

    @contextmanager
    def session(self):
        with get_db() as session:
            yield session

    async def create_user(self, user_input: Dict) -> Dict:
        with self.session() as db:
            user = User(**user_input)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.__dict__

    async def get_user(self, user_input: Dict) -> Optional[Dict]:
        with self.session() as db:
            user = db.query(User).filter_by(public_key=user_input["public_key"]).first()
            return user.__dict__ if user else None

    async def create_agent_run(self, agent_run_input: AgentRunInput) -> Dict:
        with self.session() as db:
            agent_run = AgentRun(**agent_run_input.model_dict())
            db.add(agent_run)
            db.commit()
            db.refresh(agent_run)
            return agent_run.__dict__

    async def update_agent_run(self, agent_run_id: int, agent_run: AgentRunSchema) -> bool:
        with self.session() as db:
            if isinstance(agent_run, AgentRunSchema):
                agent_run = agent_run.model_dict()
            db_agent_run = db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
            if db_agent_run:
                for key, value in agent_run.items():
                    setattr(db_agent_run, key, value)
                db.commit()
                return True
            return False

    async def list_agent_runs(self, agent_run_id=None) -> List[Dict]:
        with self.session() as db:
            if agent_run_id:
                return db.query(AgentRun).filter(AgentRun.id == agent_run_id).first().__dict__
            return [run.__dict__ for run in db.query(AgentRun).all()]

    async def delete_agent_run(self, agent_run_id: int) -> bool:
        with self.session() as db:
            agent_run = db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
            if agent_run:
                db.delete(agent_run)
                db.commit()
                return True
            return False

    async def query(self, query: str) -> List:
        with self.session() as db:
            # Raw SQL queries should be used carefully. Consider using SQLAlchemy's ORM methods instead.
            result = db.execute(query)
            return result.fetchall()

    async def connect(self):
        self.is_authenticated = True
        return True, None, None

    async def close(self):
        # No need to explicitly close as it's handled by the context manager
        self.is_authenticated = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()