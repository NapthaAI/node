DEFINE TABLE consume SCHEMAFULL
    PERMISSIONS
        FOR CREATE
            WHERE $auth.id=consumer
        FOR SELECT
            WHERE $auth.id=consumer
        FOR UPDATE
            WHERE $auth.id=consumer
        FOR DELETE
            WHERE $auth.id=consumer
            AND reply=NONE
;

DEFINE FIELD consumer ON TABLE consume TYPE record<user>
    VALUE $auth.id or $value
    DEFAULT $auth.id
    PERMISSIONS FOR UPDATE NONE
;
DEFINE FIELD module_id ON consume TYPE string DEFAULT NONE;
DEFINE FIELD module_params ON TABLE consume FLEXIBLE TYPE option<object | null> DEFAULT NONE
    PERMISSIONS FOR UPDATE NONE
;
DEFINE FIELD docker_params ON TABLE consume FLEXIBLE TYPE option<object | null> DEFAULT NONE
    PERMISSIONS FOR UPDATE NONE
;
DEFINE FIELD reply ON TABLE consume FLEXIBLE TYPE option<object | null>
    DEFAULT NONE
;
DEFINE FIELD status ON consume TYPE string DEFAULT "created";
DEFINE FIELD job_type ON consume TYPE string DEFAULT "docker"; -- Can be 'docker' or 'template'
DEFINE FIELD error ON consume TYPE option<bool> DEFAULT false;
DEFINE FIELD error_message ON consume TYPE option<string | null>;