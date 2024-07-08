DEFINE TABLE node SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $scope = 'user'
        FOR update, delete WHERE owner = $auth.id;
DEFINE FIELD public_key ON node TYPE string;
DEFINE FIELD arch ON node TYPE string;
DEFINE FIELD os ON node TYPE string;
DEFINE FIELD num_gpus ON node TYPE number;
DEFINE FIELD ollama_models ON node FLEXIBLE TYPE array;
DEFINE FIELD vram ON node TYPE option<number>;
DEFINE FIELD ram ON node TYPE option<number>;
DEFINE FIELD ip ON node TYPE option<string|null>;
DEFINE FIELD port ON node TYPE option<number|null>;
DEFINE FIELD routing ON node TYPE option<string|null>;
DEFINE FIELD owner ON node TYPE record<user>;