DEFINE TABLE orchestrator SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE orchestrator TYPE string;
DEFINE FIELD description ON TABLE orchestrator TYPE string;
DEFINE FIELD author ON TABLE orchestrator TYPE record<user>;
DEFINE FIELD url ON TABLE orchestrator TYPE string;
DEFINE FIELD type ON TABLE orchestrator TYPE string;
DEFINE FIELD version ON TABLE orchestrator TYPE string;