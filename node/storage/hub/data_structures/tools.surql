DEFINE TABLE toolset SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD source_url ON TABLE toolset TYPE string;
DEFINE FIELD name ON TABLE toolset TYPE string;
DEFINE FIELD description ON TABLE toolset TYPE string;
DEFINE FIELD author ON TABLE toolset TYPE string;
DEFINE FIELD type ON TABLE toolset TYPE string;
DEFINE FIELD version ON TABLE toolset TYPE string;