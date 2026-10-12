-- Contoh isi seed afiliasi EN (Track B). Sesuaikan link afiliasi milikmu!
-- Insert nyata: jalankan lewat psql / pgAdmin di container postgres.

INSERT INTO seed_en_offers (name, program, commission, url, demo_image) VALUES
  ('Notion',            'notion affiliate',  'up to 50% first year', 'https://notion.so/?ref=AFFILIASLI-KAMU', NULL),
  ('Canva',             'canva affiliate',   'up to 80% Pro',        'https://canva.com/?ref=AFFILIASLI-KAMU',  NULL),
  ('Grammarly',         'grammarly partner', '$0.20 signup / $0.02 install', 'https://grammarly.com/?aff= AFFILIASLI-KAMU', NULL),
  ('NordVPN',           'nord direct',       '40% per sale',         'https://nordvpn.com/?ref=AFFILIASLI-KAMU', NULL),
  ('Hostinger',         'hostinger direct',  '60% per sale',         'https://hostinger.com/?ref=AFFILIASLI-KAMU', NULL)
ON CONFLICT DO NOTHING;
