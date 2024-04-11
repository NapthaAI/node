DEFINE TABLE test SCHEMALESS
    PERMISSIONS
        FOR create WHERE $scope = 'user'
        FOR update WHERE owner = $auth.id OR processor.owner = $auth.id
        FOR select, update, delete WHERE owner = $auth.id;

DEFINE FIELD test ON test TYPE object;