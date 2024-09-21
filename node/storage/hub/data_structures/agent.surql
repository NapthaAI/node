DEFINE TABLE agent SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $scope = 'user'
        FOR update, delete WHERE author = $auth.id;
DEFINE FIELD name ON TABLE agent TYPE string;
DEFINE FIELD description ON TABLE agent TYPE string;
DEFINE FIELD author ON TABLE agent TYPE record<user>;
DEFINE FIELD url ON TABLE agent TYPE string;
DEFINE FIELD type ON TABLE agent TYPE string;
DEFINE FIELD version ON TABLE agent TYPE string;

DEFINE TABLE agentnet SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $scope = 'user'
        FOR update, delete WHERE author = $auth.id;
DEFINE FIELD name ON TABLE agentnet TYPE string;
DEFINE FIELD description ON TABLE agentnet TYPE string;
DEFINE FIELD author ON TABLE agentnet TYPE record<user>;
DEFINE FIELD url ON TABLE agentnet TYPE string;
DEFINE FIELD type ON TABLE agentnet TYPE string;
DEFINE FIELD version ON TABLE agentnet TYPE string;
