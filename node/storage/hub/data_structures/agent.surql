DEFINE TABLE agent SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE agent TYPE string;
DEFINE FIELD description ON TABLE agent TYPE string;
DEFINE FIELD author ON TABLE agent TYPE record<user>;
DEFINE FIELD url ON TABLE agent TYPE string;
DEFINE FIELD type ON TABLE agent TYPE string;
DEFINE FIELD version ON TABLE agent TYPE string;