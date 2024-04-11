CREATE user:seller1 SET
    name = "Test Seller 1",
    username = "seller1",
    password = crypto::argon2::generate("great-password")
;

CREATE user:buyer1 SET
    name="Test Buyer 1",
    username="buyer1",
    password=crypto::argon2::generate("buyer1pass")
;
