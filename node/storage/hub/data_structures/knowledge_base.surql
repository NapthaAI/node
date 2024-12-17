DEFINE TABLE knowledge_base SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE knowledge_base TYPE string;
DEFINE FIELD description ON TABLE knowledge_base TYPE string;
DEFINE FIELD author ON TABLE knowledge_base TYPE record<user>;
DEFINE FIELD url ON TABLE knowledge_base TYPE string;
DEFINE FIELD type ON TABLE knowledge_base TYPE string;
DEFINE FIELD version ON TABLE knowledge_base TYPE string;