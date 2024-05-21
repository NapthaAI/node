DEFINE TABLE user SCHEMAFULL
    PERMISSIONS
        FOR select FULL
        FOR update, delete WHERE id = $auth.id;

DEFINE FIELD public_key ON user TYPE string;