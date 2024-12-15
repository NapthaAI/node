DEFINE TABLE node SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $session.ac = 'user'
        FOR update, delete WHERE owner = $auth.id;

DEFINE FIELD public_key ON TABLE node TYPE string;
DEFINE FIELD arch ON TABLE node TYPE string;
DEFINE FIELD os ON TABLE node TYPE string;
DEFINE FIELD num_gpus ON TABLE node TYPE number;
DEFINE FIELD ollama_models ON TABLE node FLEXIBLE TYPE array;
DEFINE FIELD docker_jobs ON TABLE node TYPE bool;
DEFINE FIELD vram ON TABLE node TYPE option<number>;
DEFINE FIELD ram ON TABLE node TYPE option<number>;
DEFINE FIELD ip ON TABLE node TYPE option<string|null>;
DEFINE FIELD port ON TABLE node TYPE option<number|null>;
DEFINE FIELD routing ON TABLE node TYPE option<string|null>;
DEFINE FIELD owner ON TABLE node TYPE record<user>;
DEFINE FIELD num_servers ON TABLE node TYPE number;
DEFINE FIELD ports ON TABLE node TYPE option<array<number>>;
DEFINE FIELD node_type ON TABLE node TYPE string;
DEFINE FIELD servers ON TABLE node TYPE array<record<server>>;
