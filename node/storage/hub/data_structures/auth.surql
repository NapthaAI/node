DEFINE SCOPE user SESSION 7d
    SIGNIN (
        SELECT * FROM user WHERE username = $username AND crypto::argon2::compare(password, $password)
    )
    SIGNUP (
        IF (SELECT * FROM invite WHERE code = $invite) THEN
            ( CREATE user CONTENT {
                name: $name,
                username: $username,
                password: crypto::argon2::generate($password)
            } )
        ELSE
            ( RETURN false )
        END
    )
;
