-- Define the organization table
DEFINE TABLE organization SCHEMAFULL
    PERMISSIONS
        FOR CREATE, UPDATE, DELETE, SELECT FULL
;
DEFINE FIELD name ON organization TYPE string;
DEFINE FIELD image ON organization TYPE string;
DEFINE FIELD owner ON organization TYPE record<user>;

DEFINE EVENT organization_created ON TABLE organization WHEN $event = "CREATE" THEN {
    RELATE ($after.owner)->is_associated_with->$after;
};

-- Define the Category table
DEFINE TABLE category SCHEMAFULL
    PERMISSIONS
        FOR SELECT FULL
        FOR CREATE, UPDATE, DELETE NONE
;
DEFINE FIELD name ON category TYPE string;
DEFINE FIELD parent_categories ON category TYPE option<array<record<category>>>;

-- Define the Tag table
DEFINE TABLE tag SCHEMAFULL
    PERMISSIONS
        FOR SELECT FULL
        FOR CREATE, UPDATE, DELETE NONE
;
DEFINE FIELD name ON tag TYPE string;

-- Define the License table
DEFINE TABLE license SCHEMAFULL
    PERMISSIONS
        FOR CREATE, SELECT FULL
        FOR UPDATE, DELETE NONE
;
DEFINE FIELD license_type ON license TYPE string;
DEFINE FIELD details ON license TYPE string;

-- Add tag to a lot
DEFINE TABLE is_tagged SCHEMAFULL
    PERMISSIONS
        FOR CREATE, UPDATE, DELETE
            WHERE in.author = $auth.id
        FOR SELECT FULL
;
DEFINE FIELD in ON TABLE is_tagged TYPE record<lot>;
DEFINE FIELD out ON TABLE is_tagged TYPE record<tag>;

DEFINE TABLE in_category SCHEMAFULL
    PERMISSIONS
        FOR CREATE, UPDATE, DELETE
            WHERE in.author = $auth.id
        FOR SELECT FULL
;
DEFINE FIELD in ON TABLE in_category TYPE record<lot>;
DEFINE FIELD out ON TABLE in_category TYPE record<category>;

-- Add license to a lot
DEFINE TABLE has_license SCHEMAFULL
    PERMISSIONS
        FOR CREATE, UPDATE, DELETE
            WHERE in.author = $auth.id
        FOR SELECT FULL
;
DEFINE FIELD in ON TABLE has_license TYPE record<lot>;
DEFINE FIELD out ON TABLE has_license TYPE record<license>;

DEFINE TABLE is_associated_with SCHEMAFULL
    PERMISSIONS
        FOR CREATE, UPDATE, DELETE
            WHERE
                IF type::is::record(in, "lot") THEN
                    -- the auth'd user should be in the org, the lot's author should be in the org
                    (SELECT * FROM is_associated_with WHERE in=$auth.id AND out=$parent.out) AND
                    (SELECT * FROM is_associated_with WHERE in=$parent.in.author AND out=$parent.out)
                ELSE false END -- (dis)associating users to an org needs to go through requests_association
        FOR SELECT
            WHERE type::is::record(in, "lot")
            OR (SELECT * FROM is_associated_with WHERE in=$auth.id AND out=$parent.out)
;

DEFINE FIELD in ON TABLE is_associated_with
    ASSERT type::is::record($value, "user") OR type::is::record($value, "lot")
;
DEFINE FIELD out ON TABLE is_associated_with TYPE record<organization>;
DEFINE INDEX unique ON TABLE is_associated_with FIELDS in, out UNIQUE;

DEFINE TABLE requests_association_with SCHEMAFULL
    PERMISSIONS
        FOR CREATE, SELECT, UPDATE, DELETE
            WHERE
                IF type::is::record(in, "user") THEN
                    in=$auth.id
                ELSE IF type::is::record(in, "organization") THEN
                    (SELECT * FROM is_associated_with WHERE in=$auth.id AND out=$parent.in)
                END
;

DEFINE EVENT association_requested ON TABLE requests_association_with WHEN $event = "CREATE" THEN (
    IF (SELECT * FROM requests_association_with WHERE in=$after.out AND out=$after.in) THEN
        IF type::is::record($after.in, "user") THEN
            ( RELATE ($after.in)->is_associated_with->($after.out) )
        ELSE
            ( RELATE ($after.out)->is_associated_with->($after.in) )
        END
    END
);
DEFINE EVENT disassociation_requested ON TABLE requests_association_with WHEN $event = "DELETE" THEN {
    DELETE is_associated_with
        WHERE (in=$before.in AND out=$before.out)
        OR (in=$before.out AND out=$before.in)
    ;
    DELETE requests_association_with
        WHERE in=$before.out AND out=$before.in
    ;
};
DEFINE INDEX unique ON TABLE requests_association_with FIELDS in, out UNIQUE;