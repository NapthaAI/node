DEFINE TABLE module_run SCHEMAFULL
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

DEFINE FIELD consumer_id ON TABLE module_run TYPE record<user>
    VALUE $auth.id or $value
    DEFAULT $auth.id
    PERMISSIONS FOR UPDATE NONE
;
DEFINE FIELD module_name ON module_run TYPE string DEFAULT NONE;
DEFINE FIELD module_params ON TABLE module_run FLEXIBLE TYPE option<object | null> DEFAULT NONE
    PERMISSIONS FOR UPDATE NONE
;
DEFINE FIELD results ON TABLE module_run FLEXIBLE TYPE array
    DEFAULT []
;
DEFINE FIELD status ON module_run TYPE string DEFAULT "created";
DEFINE FIELD module_type ON module_run TYPE string DEFAULT "docker"; -- Can be 'docker' or 'template' or 'flow'
DEFINE FIELD error ON module_run TYPE option<bool> DEFAULT false;
DEFINE FIELD error_message ON module_run TYPE option<string | null>;
DEFINE FIELD worker_nodes ON module_run FLEXIBLE TYPE option<array | null>;
DEFINE FIELD child_runs ON module_run FLEXIBLE TYPE array DEFAULT [];
DEFINE FIELD parent_runs ON module_run FLEXIBLE TYPE array DEFAULT [];
DEFINE FIELD created_time ON module_run FLEXIBLE TYPE option<datetime | null>;
DEFINE FIELD start_processing_time ON module_run FLEXIBLE TYPE option<datetime | null>;
DEFINE FIELD completed_time ON module_run FLEXIBLE TYPE option<datetime | null>;
DEFINE FIELD duration ON module_run FLEXIBLE TYPE option<number | null>;
DEFINE FIELD module_version ON module_run TYPE string DEFAULT "0.1";
DEFINE FIELD module_url ON module_run TYPE string DEFAULT "";
