DEFINE TABLE agent SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE agent TYPE string;
DEFINE FIELD description ON TABLE agent TYPE string;
DEFINE FIELD parameters ON TABLE agent TYPE string;
DEFINE FIELD author ON TABLE agent TYPE record<user>;
DEFINE FIELD module_url ON TABLE agent TYPE string;
DEFINE FIELD module_type ON TABLE agent TYPE string;
DEFINE FIELD module_version ON TABLE agent TYPE string;
DEFINE FIELD module_entrypoint ON TABLE agent TYPE string;
DEFINE FIELD personas_urls ON TABLE agent TYPE option<array<string>>;