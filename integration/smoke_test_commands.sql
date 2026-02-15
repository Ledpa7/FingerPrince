-- Smoke test for Step 4
-- Replace USER_ID_HERE with an actual auth.users.id

insert into public.commands (user_id, command_text, status)
values
  ('USER_ID_HERE', 'whoami', 'pending'),
  ('USER_ID_HERE', '/capture', 'pending'),
  ('USER_ID_HERE', '/open notepad', 'pending'),
  ('USER_ID_HERE', 'this-command-does-not-exist', 'pending');

-- Verify latest rows
select id, user_id, command_text, status, left(coalesce(response_log, ''), 120) as log_preview, image_url, created_at
from public.commands
where user_id = 'USER_ID_HERE'
order by created_at desc
limit 20;
