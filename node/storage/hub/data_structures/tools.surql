DEFINE TABLE tool_library SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD source_url ON TABLE tool_library TYPE string;
DEFINE FIELD name ON TABLE tool_library TYPE string;
DEFINE FIELD description ON TABLE tool_library TYPE string;
DEFINE FIELD author ON TABLE tool_library TYPE record<user>;
DEFINE FIELD type ON TABLE tool_library TYPE string;
DEFINE FIELD version ON TABLE tool_library TYPE string;

DEFINE TABLE tool SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE tool TYPE string;
DEFINE FIELD description ON TABLE tool TYPE string;
DEFINE FIELD return_type ON TABLE tool TYPE string;
DEFINE FIELD return_description ON TABLE tool TYPE string;
# FK to tool_library
DEFINE FIELD library ON TABLE tool TYPE record<tool_library>;

DEFINE TABLE tool_argument SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE tool_argument TYPE string;
DEFINE FIELD description ON TABLE tool_argument TYPE string;
DEFINE FIELD type ON TABLE tool_argument TYPE string;
# FK to tool
DEFINE FIELD tool ON TABLE tool_argument TYPE record<tool>;


DEFINE TABLE tool_set SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

DEFINE FIELD name ON TABLE tool_set TYPE string;
DEFINE FIELD description ON TABLE tool_set TYPE string;

DEFINE TABLE tool_set_tool SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE author = $auth.id;

# FK to tool_set
DEFINE FIELD tool_set ON TABLE tool_set_tool TYPE record<tool_set>;
# FK to tool
DEFINE FIELD tool ON TABLE tool_set_tool TYPE record<tool>;