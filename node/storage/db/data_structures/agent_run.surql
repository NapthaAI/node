DEFINE TABLE agent_run SCHEMAFULL
    PERMISSIONS
        FOR CREATE
            WHERE $auth.id=consumer_id
        FOR SELECT
            WHERE $auth.id=consumer_id
        FOR UPDATE
            WHERE $auth.id=consumer_id
        FOR DELETE
            WHERE $auth.id=consumer_id
            AND results=NONE
;

DEFINE FIELD consumer_id ON TABLE agent_run TYPE record<user>
    VALUE $auth.id or $value
    DEFAULT $auth.id
    PERMISSIONS FOR UPDATE NONE
;
DEFINE FIELD agent_name ON agent_run TYPE string DEFAULT NONE;
DEFINE FIELD agent_run_params ON TABLE agent_run FLEXIBLE TYPE option<object | null> DEFAULT NONE
    PERMISSIONS FOR UPDATE NONE
;
DEFINE FIELD results ON TABLE agent_run FLEXIBLE TYPE array
    DEFAULT []
;
DEFINE FIELD status ON agent_run TYPE string DEFAULT "created";
DEFINE FIELD agent_run_type ON agent_run TYPE string DEFAULT "docker"; -- Can be 'docker' or 'package' 
DEFINE FIELD error ON agent_run TYPE option<bool> DEFAULT false;
DEFINE FIELD error_message ON agent_run TYPE option<string | null>;
DEFINE FIELD worker_nodes ON agent_run FLEXIBLE TYPE option<array | null>;
DEFINE FIELD child_runs ON agent_run FLEXIBLE TYPE array DEFAULT [];
DEFINE FIELD parent_runs ON agent_run FLEXIBLE TYPE array DEFAULT [];
DEFINE FIELD created_time ON agent_run FLEXIBLE TYPE option<datetime | null>;
DEFINE FIELD start_processing_time ON agent_run FLEXIBLE TYPE option<datetime | null>;
DEFINE FIELD completed_time ON agent_run FLEXIBLE TYPE option<datetime | null>;
DEFINE FIELD duration ON agent_run FLEXIBLE TYPE option<number | null>;
DEFINE FIELD agent_version ON agent_run TYPE option<string | null> DEFAULT "0.1";
DEFINE FIELD agent_source_url ON agent_run TYPE option<string | null> DEFAULT "";
