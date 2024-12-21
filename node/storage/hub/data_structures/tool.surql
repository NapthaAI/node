DEFINE TABLE tool SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE tool TYPE string;
DEFINE FIELD description ON TABLE tool TYPE string;
DEFINE FIELD parameters ON TABLE tool TYPE string;
DEFINE FIELD author ON TABLE tool TYPE record<user>;
DEFINE FIELD module_url ON TABLE tool TYPE string;
DEFINE FIELD module_type ON TABLE tool TYPE string;
DEFINE FIELD module_version ON TABLE tool TYPE string;
DEFINE FIELD module_entrypoint ON TABLE tool TYPE string;