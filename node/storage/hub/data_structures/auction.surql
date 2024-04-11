# LOTS
DEFINE TABLE lot SCHEMALESS
    PERMISSIONS
        FOR CREATE, SELECT FULL 
        FOR UPDATE, DELETE NONE
    -- allowing updates, deletes could be tricky!
;
DEFINE FIELD name ON TABLE lot TYPE string;
DEFINE FIELD description ON TABLE lot TYPE string;
DEFINE FIELD author ON TABLE lot TYPE record<user>
    VALUE $auth.id OR $value
    DEFAULT $auth.id
;

# AUCTIONS
DEFINE TABLE auction SCHEMAFULL
    PERMISSIONS
        FOR CREATE, DELETE
            WHERE published = false
            AND consigner = $auth.id
        FOR SELECT
            WHERE published = true
            OR consigner = $auth.id
        FOR UPDATE 
            WHERE published = false
            AND consigner = $auth.id
;
DEFINE FIELD published ON TABLE auction TYPE bool
    VALUE IF $before = NONE THEN false ELSE $value END
    DEFAULT false
    PERMISSIONS
        FOR UPDATE
            NONE
;
DEFINE FIELD hammer_time ON TABLE auction TYPE datetime
    VALUE IF $before = NONE THEN time::now() ELSE $value END
    DEFAULT time::now()
    PERMISSIONS FOR UPDATE NONE
;
DEFINE FIELD consigner ON TABLE auction TYPE record<user>
    VALUE $before OR $auth.id OR $value
    DEFAULT $auth.id
    PERMISSIONS FOR UPDATE NONE 
;
DEFINE FIELD listing ON TABLE auction TYPE record<lot>;
DEFINE FIELD buy_it_now_price ON TABLE auction TYPE option<float>
    DEFAULT NONE
;

DEFINE FIELD node ON TABLE auction TYPE record<node>;

DEFINE TABLE requests_to_publish SCHEMALESS
    PERMISSIONS
        FOR CREATE, SELECT
            WHERE in = $auth.id
        FOR UPDATE, DELETE NONE
;
DEFINE FIELD in ON TABLE requests_to_publish TYPE record<user>;
DEFINE FIELD out ON TABLE requests_to_publish TYPE record<auction>
    ASSERT in = out.consigner AND out.published = false
;
DEFINE INDEX once ON TABLE requests_to_publish FIELDS in, out UNIQUE;
DEFINE EVENT requests_to_publish ON TABLE requests_to_publish WHEN $event = "CREATE" THEN {
    -- TODO: check if permitted (fee paid or reputation exists)
    UPDATE $after.out MERGE {
        published: true,
        hammer_time: time::now() + 1w, -- for now, just default to 1w length
    };
    DELETE $after;
};

DEFINE TABLE is_top_1_bid_on AS
    SELECT
        id AS out,
        (SELECT id FROM (SELECT * FROM bids WHERE out=$parent.id ORDER BY amount DESC LIMIT 1))[0]["id"] AS in
    FROM auction
    PERMISSIONS NONE
;

DEFINE TABLE is_top_2_bid_on AS
    SELECT
        id AS out,
        (SELECT id FROM (SELECT * FROM bids WHERE out=$parent.id ORDER BY amount DESC LIMIT 2))[1]["id"] AS in
    FROM auction
    PERMISSIONS NONE
;

-- nested LET would be great here... alas
-- TODO: use intermediate view to avoid recomputing
-- user->wins->auction (amount is how much they need to pay)
DEFINE TABLE wins AS
    SELECT
        id AS out,
        (SELECT in.in FROM is_top_1_bid_on WHERE out=$parent.id)[0]["in"]["in"] AS in,
        IF buy_it_now_price != NONE AND (SELECT in.amount FROM is_top_1_bid_on WHERE out=$parent.id)[0]["in"]["amount"] >= buy_it_now_price THEN
            (buy_it_now_price)
        ELSE
            ((SELECT in.amount FROM is_top_2_bid_on WHERE out=$parent.id)[0]["in"]["amount"] ?? (SELECT in.amount FROM is_top_1_bid_on WHERE out=$parent.id)[0]["in"]["amount"])
        END AS amount
    FROM auction
    WHERE published AND time::now() > hammer_time
    PERMISSIONS
        FOR SELECT FULL
        FOR CREATE, UPDATE, DELETE NONE -- unsure if necessary for views
;

# BIDS
DEFINE TABLE bids SCHEMALESS
    PERMISSIONS
        FOR SELECT 
            WHERE in = $auth.id
        FOR CREATE, UPDATE, DELETE 
            NONE
;
DEFINE FIELD amount ON TABLE bids TYPE float;
DEFINE FIELD in ON TABLE bids TYPE record<user>;
DEFINE FIELD out ON TABLE bids TYPE record<auction>;

DEFINE TABLE requests_to_bid_on SCHEMALESS
    PERMISSIONS
        FOR CREATE, SELECT
            WHERE in = $auth.id
        FOR UPDATE, DELETE NONE
;
DEFINE FIELD amount ON TABLE requests_to_bid_on TYPE float;
DEFINE FIELD in ON TABLE requests_to_bid_on TYPE record<user>;
DEFINE FIELD out ON TABLE requests_to_bid_on TYPE record<auction>;

DEFINE INDEX once ON TABLE bids FIELDS in, out UNIQUE;
DEFINE INDEX once ON TABLE requests_to_bid_on FIELDS in, out UNIQUE;

DEFINE EVENT requests_to_bid_on ON TABLE requests_to_bid_on WHEN $event = "CREATE" THEN {
    -- TODO: check if permitted (payment method checks out, funds available, etc.)
    LET $bid = SELECT * FROM bids WHERE in=($after.in) AND out=($after.out);
    IF $bid THEN
        ( UPDATE $bid MERGE { amount: $after.amount } )
    ELSE
        ( RELATE ($after.in)->bids->($after.out) SET amount = $after.amount )
    END;
    IF $after.out.buy_it_now_price != NONE AND $after.amount >= $after.out.buy_it_now_price THEN
        ( UPDATE $after.out MERGE { hammer_time: time::now() } )
    END;
    DELETE $after;
};

# REPUTATION
DEFINE TABLE rates SCHEMALESS
    PERMISSIONS FOR CREATE, SELECT, UPDATE, DELETE
        WHERE in = $auth.id
;
DEFINE FIELD rating ON TABLE rates TYPE bool DEFAULT true;
DEFINE FIELD auction ON TABLE rates TYPE record<auction>
    ASSERT auction.consigner = out;
DEFINE FIELD in ON TABLE rates TYPE record<user>
    ASSERT (SELECT * FROM wins WHERE in=$parent.in AND out=$parent.auction)
;
DEFINE FIELD out ON TABLE rates TYPE record<user>;

DEFINE INDEX once ON TABLE rates FIELDS in, out, auction UNIQUE;

DEFINE TABLE seller AS
    SELECT
        out.consigner AS user,
        out.listing AS listing
    FROM wins
    WHERE in
    PERMISSIONS FOR CREATE, SELECT, UPDATE, DELETE NONE
;
DEFINE TABLE seller_unique AS
    SELECT user, listing FROM seller GROUP BY user, listing
    PERMISSIONS FOR CREATE, SELECT, UPDATE, DELETE NONE
;
DEFINE TABLE rating_inner AS
    SELECT
        out.consigner AS user,
        out.hammer_time AS hammer_time,
        out.listing AS listing,
        (SELECT rating FROM rates WHERE out=$parent.out.consigner AND auction=$parent.out)[0]["rating"] ?? true AS rating
    FROM wins
    WHERE in
    PERMISSIONS FOR CREATE, SELECT, UPDATE, DELETE NONE
;
DEFINE TABLE rating AS
    SELECT
        user,
        listing AS lot,
        (function((SELECT * FROM rating_inner WHERE user=$parent.user AND listing=$parent.listing)) {
            let val = arguments[0];
            val.sort(function(l, r) {
                return new Date(r.hammer_time) - new Date(l.hammer_time);
            });
            return val[0];
        })["rating"] AS rating
    FROM seller_unique
    PERMISSIONS
        FOR SELECT FULL
        FOR CREATE, UPDATE, DELETE NONE
;