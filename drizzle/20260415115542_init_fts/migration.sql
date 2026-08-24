DO $$ BEGIN
  CREATE EXTENSION IF NOT EXISTS zhparser;
EXCEPTION WHEN OTHERS THEN
  NULL;
END $$;
--> statement-breakpoint
DO $$ BEGIN
  CREATE TEXT SEARCH CONFIGURATION mixed (PARSER = zhparser);
EXCEPTION
  WHEN undefined_object THEN
    CREATE TEXT SEARCH CONFIGURATION mixed (COPY = pg_catalog.simple);
  WHEN duplicate_object THEN
    NULL;
END $$;
--> statement-breakpoint
DO $$ BEGIN
  ALTER TEXT SEARCH CONFIGURATION mixed
  ADD MAPPING FOR n,v,a,b,z,s,t,i,j,l,x,g,m,q,d,f WITH simple;
EXCEPTION WHEN OTHERS THEN
  NULL;
END $$;
--> statement-breakpoint
DO $$ BEGIN
  ALTER TEXT SEARCH CONFIGURATION mixed
  ADD MAPPING FOR e WITH english_stem;
EXCEPTION WHEN OTHERS THEN
  NULL;
END $$;
