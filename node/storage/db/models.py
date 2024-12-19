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

class OrchestratorRun(Base):
    __tablename__ = 'orchestrator_runs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    consumer_id = Column(String, ForeignKey('users.id'), nullable=False)
    inputs = Column(JSON)
    orchestrator_deployment = Column(JSON, nullable=False)
    status = Column(String, default="pending")
    error = Column(Boolean, default=False)
    results = Column(ARRAY(String), default=[])
    error_message = Column(String)
    created_time = Column(DateTime)
    start_processing_time = Column(DateTime)
    completed_time = Column(DateTime)
    duration = Column(Integer)  # Changed from float to integer for consistency with AgentRun
    input_schema_ipfs_hash = Column(String)

    consumer = relationship("User", back_populates="orchestrator_runs")

class EnvironmentRun(Base):
    __tablename__ = 'environment_runs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    consumer_id = Column(String, ForeignKey('users.id'), nullable=False)
    inputs = Column(JSON)
    environment_deployment = Column(JSON, nullable=False)
    orchestrator_runs = Column(JSONB, default=[])
    status = Column(String, default="pending")
    error = Column(Boolean, default=False)
    results = Column(ARRAY(String), default=[])
    error_message = Column(String)
    created_time = Column(DateTime)
    start_processing_time = Column(DateTime)
    completed_time = Column(DateTime)
    duration = Column(Integer)
    input_schema_ipfs_hash = Column(String)

    consumer = relationship("User", back_populates="environment_runs")

class KBRun(Base):
    __tablename__ = 'kb_runs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    consumer_id = Column(String, ForeignKey('users.id'), nullable=False)
    inputs = Column(JSON)
    kb_deployment = Column(JSON, nullable=False)
    orchestrator_runs = Column(JSONB, default=[])
    status = Column(String, default="pending")
    error = Column(Boolean, default=False)
    results = Column(ARRAY(String), default=[])
    error_message = Column(String)
    created_time = Column(DateTime)
    start_processing_time = Column(DateTime)
    completed_time = Column(DateTime)
    duration = Column(Integer)

    consumer = relationship("User", back_populates="kb_runs")

User.agent_runs = relationship("AgentRun", order_by=AgentRun.id, back_populates="consumer")
User.orchestrator_runs = relationship("OrchestratorRun", back_populates="consumer")
User.environment_runs = relationship("EnvironmentRun", back_populates="consumer")
User.kb_runs = relationship("KBRun", back_populates="consumer")