import logging
from contextlib import contextmanager
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from tenacity import retry, stop_after_attempt, wait_exponential
import threading

from node.schemas import AgentRunInput
from node.storage.db.models import User, AgentRun
from node.config import LOCAL_DB_URL
from node.schemas import AgentRun as AgentRunSchema

logger = logging.getLogger(__name__)

class DatabasePool:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.engine = create_engine(
            LOCAL_DB_URL,
            poolclass=QueuePool,
            pool_size=40,          
            max_overflow=160,      
            pool_timeout=20,       
            pool_recycle=3600,     # 1 hour recycle
            pool_pre_ping=True,    
            echo=False,
            connect_args={
                'keepalives': 1,
                'keepalives_idle': 60,
                'keepalives_interval': 10,
                'keepalives_count': 5,
                'options': '-c statement_timeout=60000'
            }
        )
        
        self.session_factory = scoped_session(
            sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False
            )
        )

    def dispose(self):
        if hasattr(self, 'engine'):
            self.engine.dispose()

class DB:
    def __init__(self):
        self.is_authenticated = False
        self.pool = DatabasePool()
        self._session = None

    @contextmanager
    def session(self):
        if self._session is None:
            self._session = self.pool.session_factory()
        
        try:
            yield self._session
        except SQLAlchemyError as e:
            if self._session:
                self._session.rollback()
            logger.error(f"Database error: {str(e)}")
            raise
        finally:
            if self._session:
                self._session.close()
                self._session = None

    def get_pool_stats(self) -> Dict:
        return {
            'size': self.pool.engine.pool.size(),
            'checkedin': self.pool.engine.pool.checkedin(),
            'overflow': self.pool.engine.pool.overflow(),
            'checkedout': self.pool.engine.pool.checkedout(),
        }

    async def create_user(self, user_input: Dict) -> Dict:
        try:
            with self.session() as db:
                user = User(**user_input)
                db.add(user)
                db.commit()
                db.refresh(user)
                return user.__dict__
        except SQLAlchemyError as e:
            logger.error(f"Failed to create user: {str(e)}")
            raise

    async def get_user(self, user_input: Dict) -> Optional[Dict]:
        try:
            with self.session() as db:
                user = db.query(User).filter_by(public_key=user_input["public_key"]).first()
                return user.__dict__ if user else None
        except SQLAlchemyError as e:
            logger.error(f"Failed to get user: {str(e)}")
            raise

    async def create_agent_run(self, agent_run_input: AgentRunInput) -> Dict:
        try:
            with self.session() as db:
                agent_run = AgentRun(**agent_run_input.model_dict())
                db.add(agent_run)
                db.commit()
                db.refresh(agent_run)
                return agent_run.__dict__
        except SQLAlchemyError as e:
            logger.error(f"Failed to create agent run: {str(e)}")
            raise

    async def update_agent_run(self, agent_run_id: int, agent_run: AgentRunSchema) -> bool:
        try:
            with self.session() as db:
                if isinstance(agent_run, AgentRunSchema):
                    agent_run = agent_run.model_dict()
                db_agent_run = db.query(AgentRun).filter(
                    AgentRun.id == agent_run_id
                ).first()
                if db_agent_run:
                    for key, value in agent_run.items():
                        setattr(db_agent_run, key, value)
                    db.commit()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Failed to update agent run: {str(e)}")
            raise

    async def list_agent_runs(self, agent_run_id=None) -> List[Dict]:
        try:
            with self.session() as db:
                if agent_run_id:
                    result = db.query(AgentRun).filter(
                        AgentRun.id == agent_run_id
                    ).first()
                    return result.__dict__ if result else None
                return [run.__dict__ for run in db.query(AgentRun).all()]
        except SQLAlchemyError as e:
            logger.error(f"Failed to list agent runs: {str(e)}")
            raise

    async def delete_agent_run(self, agent_run_id: int) -> bool:
        try:
            with self.session() as db:
                agent_run = db.query(AgentRun).filter(
                    AgentRun.id == agent_run_id
                ).first()
                if agent_run:
                    db.delete(agent_run)
                    db.commit()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Failed to delete agent run: {str(e)}")
            raise

    async def query(self, query_str: str) -> List:
        try:
            with self.session() as db:
                result = db.execute(text(query_str))
                return result.fetchall()
        except SQLAlchemyError as e:
            logger.error(f"Failed to execute query: {str(e)}")
            raise

    async def check_connection_health(self) -> bool:
        try:
            with self.session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False

    async def get_connection_stats(self) -> Dict:
        try:
            with self.session() as db:
                result = db.execute(text("""
                    SELECT count(*) as connection_count 
                    FROM pg_stat_activity 
                    WHERE datname = current_database()
                """))
                return dict(result.fetchone())
        except Exception as e:
            logger.error(f"Failed to get connection stats: {str(e)}")
            return {}

    async def create_multiple_agent_runs(self, agent_runs: List[AgentRunInput]) -> List[Dict]:
        try:
            with self.session() as db:
                runs = [AgentRun(**run.model_dict()) for run in agent_runs]
                db.add_all(runs)
                db.commit()
                return [run.__dict__ for run in runs]
        except SQLAlchemyError as e:
            logger.error(f"Failed to create agent runs: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2)
    )
    async def connect(self):
        self.is_authenticated = await self.check_connection_health()
        return self.is_authenticated, None, None

    async def close(self):
        self.is_authenticated = False
        if self._session:
            self._session.close()
            self._session = None
        self.pool.dispose()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()