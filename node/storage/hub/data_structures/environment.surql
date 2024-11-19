DEFINE TABLE environment SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE environment TYPE string;
DEFINE FIELD description ON TABLE environment TYPE string;
DEFINE FIELD author ON TABLE environment TYPE record<user>;
DEFINE FIELD url ON TABLE environment TYPE string;
DEFINE FIELD type ON TABLE environment TYPE string;
DEFINE FIELD version ON TABLE environment TYPE string;