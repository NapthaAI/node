DEFINE TABLE module SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $scope = 'user'
        FOR update, delete WHERE user_id = $auth.id;
DEFINE FIELD name ON TABLE module TYPE string;
DEFINE FIELD description ON TABLE module TYPE string;
DEFINE FIELD author ON TABLE module TYPE record<user>;
DEFINE FIELD url ON TABLE module TYPE string;
DEFINE FIELD type ON TABLE module TYPE string;
