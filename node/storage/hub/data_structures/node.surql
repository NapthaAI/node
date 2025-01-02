DEFINE TABLE node SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE owner = $auth.id;

DEFINE FIELD owner ON TABLE node TYPE record<user>;
DEFINE FIELD public_key ON TABLE node TYPE string;
DEFINE FIELD ip ON TABLE node TYPE string;
DEFINE FIELD server_type ON TABLE node TYPE string;
DEFINE FIELD http_port ON TABLE node TYPE number;
DEFINE FIELD num_servers ON TABLE node TYPE number;
DEFINE FIELD provider_types ON TABLE node TYPE array<string>;
DEFINE FIELD servers ON TABLE node TYPE array<record<server>>;
DEFINE FIELD models ON TABLE node FLEXIBLE TYPE array;
DEFINE FIELD docker_jobs ON TABLE node TYPE bool;
DEFINE FIELD routing_type ON TABLE node TYPE option<string>;
DEFINE FIELD routing_url ON TABLE node TYPE option<string|null>;
DEFINE FIELD num_gpus ON TABLE node TYPE option<number>;
DEFINE FIELD arch ON TABLE node TYPE option<string>;
DEFINE FIELD os ON TABLE node TYPE option<string>;
DEFINE FIELD ram ON TABLE node TYPE option<number>;
DEFINE FIELD vram ON TABLE node TYPE option<number>;

DEFINE TABLE server SCHEMAFULL
    PERMISSIONS 
        FOR create, select, update, delete WHERE true;

DEFINE FIELD server_type ON TABLE server TYPE string;
DEFINE FIELD port ON TABLE server TYPE number;
DEFINE FIELD node_id ON TABLE server TYPE string;
