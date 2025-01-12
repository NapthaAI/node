DEFINE TABLE environment SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE environment TYPE string;
DEFINE FIELD description ON TABLE environment TYPE string;
DEFINE FIELD parameters ON TABLE environment TYPE string;
DEFINE FIELD author ON TABLE environment TYPE record<user>;
DEFINE FIELD module_url ON TABLE environment TYPE string;
DEFINE FIELD module_type ON TABLE environment TYPE string;
DEFINE FIELD module_version ON TABLE environment TYPE string;
DEFINE FIELD module_entrypoint ON TABLE environment TYPE string;
DEFINE FIELD execution_type ON TABLE environment TYPE string;