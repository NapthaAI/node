import asyncio
import logging
import threading
import json
from contextlib import contextmanager
from psycopg2.extras import Json
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Dict, List, Optional, Union, Any

from node.config import LOCAL_DB_URL
from node.storage.db.models import AgentRun, OrchestratorRun, EnvironmentRun, User, KBRun
from node.schemas import (
    AgentRun as AgentRunSchema, 
    OrchestratorRun as OrchestratorRunSchema,
    EnvironmentRun as EnvironmentRunSchema,
    AgentRunInput,
    OrchestratorRunInput,
    EnvironmentRunInput,
    KBRunInput,
    KBRun as KBRunSchema
)

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
            pool_size=120,          # Base pool size
            max_overflow=240,      # More overflow for 120 workers
            pool_timeout=30,
            pool_recycle=300,      # 5 minute recycle
            pool_pre_ping=True,
            echo=False,
            connect_args={
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
                'options': '-c statement_timeout=30000'  # 30 second timeout
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

        self._setup_engine_events()

    def _setup_engine_events(self):
        @event.listens_for(self.engine, 'checkout')
        def on_checkout(dbapi_conn, connection_rec, connection_proxy):
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute('SELECT 1')
                cursor.close()
            except Exception:
                logger.error("Connection verification failed")
                raise OperationalError("Invalid connection")

    def dispose(self):
        """Dispose the engine and all connections"""
        if hasattr(self, 'engine'):
            self.engine.dispose()

class DB:
    def __init__(self):
        self.is_authenticated = False
        self.pool = DatabasePool()

    @contextmanager
    def session(self):
        session = self.pool.session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Database error: {str(e)}")
            raise
        finally:
            session.close()
            self.pool.session_factory.remove()

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
                db.flush()
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

    async def create_module_run(self, run_input: Union[Dict, any], run_type: str) -> Union[AgentRunSchema, OrchestratorRunSchema, EnvironmentRunSchema]:
        model_map = {
            'agent': (AgentRun, AgentRunSchema),
            'orchestrator': (OrchestratorRun, OrchestratorRunSchema),
            'environment': (EnvironmentRun, EnvironmentRunSchema),
            'knowledge_base': (KBRun, KBRunSchema)
        }
        
        try:
            Model, Schema = model_map[run_type]
            with self.session() as db:
                if hasattr(run_input, 'model_dump'):
                    run = Model(**run_input.model_dump())
                else:
                    run = Model(**run_input)
                db.add(run)
                db.flush()
                db.refresh(run)
                logger.info(f"Created {run_type} run: {run.__dict__}")
                return Schema(**run.__dict__)
        except SQLAlchemyError as e:
            logger.error(f"Failed to create {run_type} run: {str(e)}")
            raise

    async def create_agent_run(self, agent_run_input: Union[AgentRunInput, Dict]) -> AgentRunSchema:
        return await self.create_module_run(agent_run_input, 'agent')

    async def create_orchestrator_run(self, orchestrator_run_input: Union[OrchestratorRunInput, Dict]) -> OrchestratorRunSchema:
        return await self.create_module_run(orchestrator_run_input, 'orchestrator')

    async def create_environment_run(self, environment_run_input: Union[EnvironmentRunInput, Dict]) -> EnvironmentRunSchema:
        return await self.create_module_run(environment_run_input, 'environment')

    async def create_kb_run(self, kb_run_input: Union[KBRunInput, Dict]) -> KBRunSchema:
        return await self.create_module_run(kb_run_input, 'knowledge_base')

    async def update_run(self, run_id: int, run_data: Union[AgentRunSchema, OrchestratorRunSchema, EnvironmentRunSchema], run_type: str) -> bool:
        model_map = {
            'agent': AgentRun,
            'orchestrator': OrchestratorRun,
            'environment': EnvironmentRun,
            'knowledge_base': KBRun
        }
        
        try:
            Model = model_map[run_type]
            with self.session() as db:
                if hasattr(run_data, 'model_dump'):
                    run_data = run_data.model_dump()
                db_run = db.query(Model).filter(Model.id == run_id).first()
                if db_run:
                    for key, value in run_data.items():
                        setattr(db_run, key, value)
                    db.flush()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Failed to update {run_type} run: {str(e)}")
            raise

    async def update_agent_run(self, run_id: int, run_data: AgentRunSchema) -> bool:
        return await self.update_run(run_id, run_data, 'agent')

    async def update_orchestrator_run(self, run_id: int, run_data: OrchestratorRunSchema) -> bool:
        return await self.update_run(run_id, run_data, 'orchestrator')

    async def update_environment_run(self, run_id: int, run_data: EnvironmentRunSchema) -> bool:
        return await self.update_run(run_id, run_data, 'environment')
    
    async def update_kb_run(self, run_id: int, run_data: KBRunSchema) -> bool:
        return await self.update_run(run_id, run_data, 'knowledge_base')

    async def list_module_runs(self, run_type: str, run_id: Optional[int] = None) -> Union[Dict, List[Dict], None]:
        model_map = {
            'agent': AgentRun,
            'orchestrator': OrchestratorRun,
            'environment': EnvironmentRun,
            'knowledge_base': KBRun
        }
        
        max_retries = 3
        retry_delay = 1  # seconds
        Model = model_map[run_type]
        
        for attempt in range(max_retries):
            try:
                with self.session() as db:
                    if run_id:
                        result = db.query(Model).filter(
                            Model.id == run_id
                        ).first()
                        if not result:
                            logger.warning(f"{run_type.capitalize()} run {run_id} not found on attempt {attempt + 1}")
                            await asyncio.sleep(retry_delay)
                            continue
                        return result.__dict__ if result else None
                    return [run.__dict__ for run in db.query(Model).all()]
            except SQLAlchemyError as e:
                logger.error(f"Database error on attempt {attempt + 1}: {str(e)}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(retry_delay)

    # Replace existing list functions with these wrapper methods
    async def list_agent_runs(self, agent_run_id=None) -> Union[Dict, List[Dict], None]:
        return await self.list_module_runs('agent', agent_run_id)

    async def list_orchestrator_runs(self, orchestrator_run_id=None) -> Union[Dict, List[Dict], None]:
        return await self.list_module_runs('orchestrator', orchestrator_run_id)

    # Optional: Add environment runs support
    async def list_environment_runs(self, environment_run_id=None) -> Union[Dict, List[Dict], None]:
        return await self.list_module_runs('environment', environment_run_id)

    async def delete_agent_run(self, agent_run_id: int) -> bool:
        try:
            with self.session() as db:
                agent_run = db.query(AgentRun).filter(
                    AgentRun.id == agent_run_id
                ).first()
                if agent_run:
                    db.delete(agent_run)
                    db.flush()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Failed to delete agent run: {str(e)}")
            raise

    async def delete_orchestrator_run(self, orchestrator_run_id: int) -> bool:
        try:
            with self.session() as db:
                orchestrator_run = db.query(OrchestratorRun).filter(
                    OrchestratorRun.id == orchestrator_run_id
                ).first()
                if orchestrator_run:
                    db.delete(orchestrator_run)
                    db.flush()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Failed to delete orchestrator run: {str(e)}")
            raise

    async def query(self, query_str: str) -> List:
        try:
            with self.session() as db:
                result = db.execute(text(query_str))
                return result.fetchall()
        except SQLAlchemyError as e:
            logger.error(f"Failed to execute query: {str(e)}")
            raise

    def _get_sqlalchemy_type(self, pg_type: str):
        """Convert PostgreSQL type to SQLAlchemy type"""
        from sqlalchemy import String, Integer, Float, Boolean, ARRAY, TIMESTAMP, JSON
        from sqlalchemy.dialects.postgresql import JSONB
        
        type_map = {
            'text': String,
            'integer': Integer,
            'float': Float,
            'boolean': Boolean,
            'jsonb': JSONB,  # Use PostgreSQL-specific JSONB
            'timestamp': TIMESTAMP
        }
        
        # Handle array types
        if pg_type.endswith('[]'):
            base_type = pg_type[:-2]
            if base_type == 'text':
                return ARRAY(String)
            elif base_type == 'integer':
                return ARRAY(Integer)
            elif base_type == 'float':
                return ARRAY(Float)
            else:
                raise ValueError(f"Unsupported array type: {base_type}")
                
        return type_map.get(pg_type)

    async def create_dynamic_table(self, table_name: str, schema: Dict[str, Dict[str, Any]]) -> bool:
        """Create table dynamically using SQLAlchemy"""
        from sqlalchemy import MetaData, Table, Column
        try:
            metadata = MetaData()
            columns = []
            
            for field_name, properties in schema.items():
                # Convert type to lowercase
                field_type_str = properties['type'].lower()
                field_type = self._get_sqlalchemy_type(field_type_str)
                
                if not field_type:
                    raise ValueError(f"Unsupported type: {field_type_str}")
                    
                # For non-array types, we need to call the type
                if not field_type_str.endswith('[]'):
                    field_type = field_type()
                    
                column_args = {
                    'primary_key': properties.get('primary_key', False),
                    'nullable': not properties.get('required', False)
                }
                
                if 'default' in properties:
                    column_args['default'] = properties['default']
                    
                columns.append(Column(field_name, field_type, **column_args))

            Table(table_name, metadata, *columns)
            metadata.create_all(self.pool.engine)
            return True
            
        except Exception as e:
            logger.error(f"Failed to create table: {str(e)}")
            raise

    async def add_dynamic_row(self, table_name: str, data: Dict[str, Any], 
                            schema: Optional[Dict[str, Dict[str, Any]]] = None) -> bool:
        """Add row to dynamically created table"""
        try:
            with self.session() as db:
                # First, get the column types from the database
                type_query = text("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = :table_name
                """)
                result = db.execute(type_query, {"table_name": table_name})
                column_types = {row[0]: row[1] for row in result}

                # Process the data based on column types
                processed_data = {}
                for key, value in data.items():
                    if key in column_types:
                        col_type = column_types[key].lower()
                        
                        # Handle different types
                        if col_type == 'jsonb':
                            # Convert dict/list to JSON string
                            processed_data[key] = json.dumps(value)
                        elif col_type.startswith('_float'):
                            # Handle float array
                            processed_data[key] = value
                        elif col_type.startswith('_'):
                            # Other arrays
                            processed_data[key] = value
                        else:
                            # Regular values
                            processed_data[key] = value

                # Construct and execute query
                columns = list(processed_data.keys())
                placeholders = [f":{col}" for col in columns]
                
                query = text(f"""
                    INSERT INTO {table_name} 
                    ({', '.join(columns)}) 
                    VALUES 
                    ({', '.join(placeholders)})
                """)

                # Execute with processed data
                db.execute(query, processed_data)
                return True

        except SQLAlchemyError as e:
            logger.error(f"Failed to add row: {str(e)}")
            logger.error(f"Data: {data}")
            logger.error(f"Processed data: {processed_data if 'processed_data' in locals() else 'Not processed'}")
            raise

    async def update_dynamic_row(self, table_name: str, data: Dict[str, Any],
                            condition: Dict[str, Any]) -> int:
        """Update rows in dynamically created table"""
        try:
            with self.session() as db:
                # Get schema information
                schema_query = text("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                """)
                result = db.execute(schema_query, {"table_name": table_name})
                schema = {row[0]: {"type": row[1]} for row in result}

                # Prepare data based on column types
                prepared_data = {}
                for key, value in data.items():
                    if key in schema:
                        col_type = schema[key].get('type', '').lower()
                        if col_type == 'jsonb' and isinstance(value, (dict, list)):
                            prepared_data[key] = json.dumps(value)
                        elif col_type.endswith('[]') and isinstance(value, list):
                            if col_type == 'text[]':
                                prepared_data[key] = value
                            else:
                                # Convert list elements to appropriate type
                                prepared_data[key] = value
                        else:
                            prepared_data[key] = value

                set_clause = ", ".join([f"{k} = :{k}" for k in prepared_data.keys()])
                where_clause = " AND ".join([f"{k} = :condition_{k}" for k in condition.keys()])
                
                # Merge prepared data and condition with prefixed condition keys
                params = {**prepared_data, **{f"condition_{k}": v for k, v in condition.items()}}
                
                query = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
                result = db.execute(text(query), params)
                return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Failed to update row: {str(e)}")
            raise

    async def delete_dynamic_row(self, table_name: str, condition: Dict[str, Any]) -> int:
        """Delete rows from dynamically created table"""
        try:
            with self.session() as db:
                where_clause = " AND ".join([f"{k} = :{k}" for k in condition.keys()])
                query = f"DELETE FROM {table_name} WHERE {where_clause}"
                result = db.execute(text(query), condition)
                return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Failed to delete row: {str(e)}")
            raise

    async def query_dynamic_table(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        condition: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query dynamically created table"""
        try:
            with self.session() as db:
                select_clause = "*" if not columns else ", ".join(columns)
                query = f"SELECT {select_clause} FROM {table_name}"
                params = {}
                
                if condition:
                    where_clause = " AND ".join([f"{k} = :{k}" for k in condition.keys()])
                    query += f" WHERE {where_clause}"
                    params.update(condition)
                
                if order_by:
                    query += f" ORDER BY {order_by}"
                    
                if limit:
                    query += f" LIMIT {limit}"
                
                result = db.execute(text(query), params)
                # Convert results to dictionaries properly
                return [dict(row._mapping) for row in result]
        except SQLAlchemyError as e:
            logger.error(f"Failed to query table: {str(e)}")
            raise

    async def list_dynamic_tables(self) -> List[str]:
        """Get list of all tables using SQLAlchemy"""
        try:
            with self.session() as db:
                query = text("""
                    SELECT tablename 
                    FROM pg_catalog.pg_tables 
                    WHERE schemaname != 'pg_catalog' 
                    AND schemaname != 'information_schema'
                """)
                result = db.execute(query)
                return [row[0] for row in result]
        except SQLAlchemyError as e:
            logger.error(f"Failed to list tables: {str(e)}")
            raise

    async def get_dynamic_table_schema(self, table_name: str) -> Dict[str, Dict[str, Any]]:
        """Get schema information for a specific table using SQLAlchemy"""
        try:
            with self.session() as db:
                query = text("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                """)
                result = db.execute(query, {"table_name": table_name})
                
                schema = {}
                for row in result:
                    schema[row[0]] = {
                        "type": row[1],
                        "required": row[2] == 'NO',
                        "default": row[3]
                    }
                return schema
        except SQLAlchemyError as e:
            logger.error(f"Failed to get table schema: {str(e)}")
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2)
    )
    async def connect(self):
        self.is_authenticated = await self.check_connection_health()
        return self.is_authenticated, None, None

    async def close(self):
        self.is_authenticated = False
        self.pool.dispose()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()