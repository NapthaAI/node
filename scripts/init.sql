-- Create the "naptha" database if it doesn't exist
DO $$BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'naptha') THEN
        CREATE DATABASE naptha;
    END IF;
END$$;

-- Create the "litellm" database if it doesn't exist
-- this is important because litellm migrates (and wipes) the public schema of
-- whatever database it is pointed at, so it can't co-locate with the app
DO $$BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm') THEN
        CREATE DATABASE litellm;
    END IF;
END$$;