DEFINE TABLE server SCHEMAFULL
    PERMISSIONS 
        FOR create, select, update, delete WHERE true;

DEFINE FIELD server_type ON TABLE server TYPE string;
DEFINE FIELD connection_string ON TABLE server TYPE string;
DEFINE FIELD node_id ON TABLE server TYPE string;
