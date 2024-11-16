from sqlalchemy import Column, String, JSON, ARRAY, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import JSONB
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True)
    public_key = Column(String, unique=True, nullable=False)

class AgentRun(Base):
    __tablename__ = 'agent_runs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    consumer_id = Column(String, ForeignKey('users.id'), nullable=False)
    inputs = Column(JSON)
    agent_deployment = Column(JSON)
    orchestrator_runs = Column(JSONB, default=[])
    status = Column(String, default="created")
    results = Column(ARRAY(JSON), default=[])
    error = Column(Boolean, default=False)
    error_message = Column(String)
    created_time = Column(DateTime)
    start_processing_time = Column(DateTime)
    completed_time = Column(DateTime)
    duration = Column(Integer)

    consumer = relationship("User", back_populates="agent_runs")

User.agent_runs = relationship("AgentRun", order_by=AgentRun.id, back_populates="consumer")