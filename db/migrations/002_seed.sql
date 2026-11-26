-- Файл seed.json остаётся редактируемым источником справочников.
CREATE TEMP TABLE seed_import(line text);
\copy seed_import FROM '/opt/killstass/seed.json' WITH (FORMAT csv, DELIMITER E'\x01', QUOTE E'\x02')
INSERT INTO catalogs(code,kind,edition,label,config)
SELECT x->>'code',x->>'kind',x->>'edition',x->>'label',x->'config'
FROM (SELECT jsonb_array_elements(string_agg(line,E'\n')::jsonb) x FROM seed_import) s
ON CONFLICT(code) DO UPDATE SET label=excluded.label,config=excluded.config;
DROP TABLE seed_import;
