DEFINE TABLE node SCHEMAFULL
    PERMISSIONS
        FOR select, create WHERE $scope = 'user'
        FOR update, delete WHERE user_id = $auth.id;
DEFINE FIELD user_id ON node TYPE record<user>;
DEFINE FIELD address ON node TYPE string;
DEFINE FIELD arch ON node TYPE string;
DEFINE FIELD os ON node TYPE string;
DEFINE FIELD num_gpus ON node TYPE number;
DEFINE FIELD vram ON node TYPE option<number>;
DEFINE FIELD ram ON node TYPE option<number>;
DEFINE FIELD workflow_type ON node FLEXIBLE TYPE array;