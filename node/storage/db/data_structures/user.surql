DEFINE TABLE user SCHEMAFULL
    PERMISSIONS
        FOR select FULL
        FOR update, delete WHERE id = $auth.id;

DEFINE FIELD name ON user TYPE string ASSERT string::len($value) >= 2;
DEFINE FIELD username ON user TYPE string VALUE string::lowercase($value);
DEFINE FIELD password ON user TYPE string PERMISSIONS FOR select NONE
    PERMISSIONS
        FOR select, update, delete WHERE id = $auth.id;

DEFINE FIELD created ON user 
    VALUE $before OR time::now()
    DEFAULT time::now()
    PERMISSIONS
        FOR select, update, delete WHERE id = $auth.id;
DEFINE FIELD updated ON user 
    VALUE time::now()
    DEFAULT time::now()
    PERMISSIONS
        FOR select, update, delete WHERE id = $auth.id;

DEFINE INDEX unique_username ON user FIELDS username UNIQUE;

DEFINE EVENT removal ON user WHEN $event = "DELETE" THEN {
    DELETE job WHERE consumer = $before.id;
};
DEFINE TABLE invite SCHEMAFULL
    PERMISSIONS FOR CREATE, SELECT, UPDATE, DELETE NONE
;
DEFINE FIELD code ON invite TYPE string;