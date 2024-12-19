DEFINE TABLE kb SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE kb TYPE string;
DEFINE FIELD description ON TABLE kb TYPE string;
DEFINE FIELD parameters ON TABLE kb TYPE string;
DEFINE FIELD author ON TABLE kb TYPE record<user>;
DEFINE FIELD module_url ON TABLE kb TYPE string;
DEFINE FIELD module_type ON TABLE kb TYPE string;
DEFINE FIELD module_version ON TABLE kb TYPE string;
DEFINE FIELD module_entrypoint ON TABLE kb TYPE string;