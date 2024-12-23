DEFINE TABLE memory SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE memory TYPE string;
DEFINE FIELD description ON TABLE memory TYPE string;
DEFINE FIELD parameters ON TABLE memory TYPE string;
DEFINE FIELD author ON TABLE memory TYPE record<user>;
DEFINE FIELD module_url ON TABLE memory TYPE string;
DEFINE FIELD module_type ON TABLE memory TYPE string;
DEFINE FIELD module_version ON TABLE memory TYPE string;
DEFINE FIELD module_entrypoint ON TABLE memory TYPE string;