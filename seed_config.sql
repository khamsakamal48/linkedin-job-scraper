-- Seed config rows for WF-D LinkedIn Poller.
-- Run on the same Postgres that WF-A uses (cred "Local Postgres account").
-- Edit and re-run anytime to change searches / interval. No redeploy needed.

-- 1) Poll interval (drives the lookback window: since = interval * 1.5).
--    Keep this in sync with the WF-D Schedule Trigger cron.
INSERT INTO app_config (key, value) VALUES
('linkedin_poll', '{"interval_seconds": 3600}'::jsonb)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

-- 2) Search list. Each block: keywords[] x locations[] is expanded to all combos
--    by WF-D "Expand Searches". Scalar keywords/location also accepted.
--    Filters (all optional, applied to every combo in the block):
--      remote     -> f_WT: "1" onsite, "2" remote, "3" hybrid
--      experience -> f_E:  "1" intern, "2" entry, "3" associate,
--                          "4" mid-senior, "5" director, "6" executive
--      jobType    -> f_JT: "F" full-time, "P" part-time, "C" contract,
--                          "T" temporary, "I" internship
--      geoId      -> LinkedIn numeric geoId (optional, more precise than text)
-- INSERT INTO app_config (key, value) VALUES
-- ('linkedin_searches', '[
--   {
--     "keywords": ["IT Head", "AI Automation", "IT Manager", "IT Director", "IT VP", "IT CIO", "IT CTO"],
--     "locations": ["Mumbai", "Pune", "Remote", "Trivandrum"],
--     "remote": 1,
--     "experience": 4,
--     "jobType": "F"
--   },
--   {
--     "keywords": "IT Head",
--     "location": "India",
--     "remote": 2
--   }
-- ]'::jsonb)
-- ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
INSERT INTO app_config (key, value) VALUES
('linkedin_searches', '[
    {
        "keywords": ["IT Head", "AI Automation", "IT Manager", "IT Director", "IT VP", "IT CIO", "IT CTO"],
        "locations": ["Mumbai, Maharashtra, India", "Pune, Maharashtra, India", "Thiruvananthapuram, Kerala, India", "India"],
        "geoId": "102713980",
        "remote": 1,
        "experience": 4,
        "jobType": "F"
    },
    {
        "keywords": ["IT Head", "AI Automation", "IT Manager", "IT Director", "IT VP", "IT CIO", "IT CTO"],
        "locations": ["Mumbai, Maharashtra, India", "Pune, Maharashtra, India", "Thiruvananthapuram, Kerala, India", "India"],
        "geoId": "102713980",
        "remote": 2,
        "experience": 4,
        "jobType": "F"
    },
    {
        "keywords": ["IT Head", "AI Automation", "IT Manager", "IT Director", "IT VP", "IT CIO", "IT CTO"],
        "locations": ["Mumbai, Maharashtra, India", "Pune, Maharashtra, India", "Thiruvananthapuram, Kerala, India", "India"],
        "geoId": "102713980",
        "remote": 3,
        "experience": 4,
        "jobType": "F"
    }
]'::jsonb)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

-- Verify:
-- SELECT key, value FROM app_config WHERE key IN ('linkedin_poll','linkedin_searches');
