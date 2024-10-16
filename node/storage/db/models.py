from sqlalchemy import Column, Integer, String, Boolean, ARRAY, JSON, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True)
    public_key = Column(String, unique=True, nullable=False)

class AgentRun(Base):
    __tablename__ = 'agent_runs'

    id = Column(Integer, primary_key=True)
    consumer_id = Column(String, ForeignKey('users.id'), nullable=False)
    agent_name = Column(String)
    agent_run_params = Column(JSON)
    results = Column(ARRAY(JSON), default=[])
    status = Column(String, default="created")
    agent_run_type = Column(String, default="docker")
    error = Column(Boolean, default=False)
    error_message = Column(String)
    worker_nodes = Column(ARRAY(String))
    child_runs = Column(ARRAY(Integer), default=[])
    parent_runs = Column(ARRAY(Integer), default=[])
    created_time = Column(DateTime)
    start_processing_time = Column(DateTime)
    completed_time = Column(DateTime)
    duration = Column(Integer)
    agent_version = Column(String, default="0.1")
    agent_source_url = Column(String, default="")

    consumer = relationship("User", back_populates="agent_runs")

User.agent_runs = relationship("AgentRun", order_by=AgentRun.id, back_populates="consumer")