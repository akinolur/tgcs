## How to get `api_id` and `api_hash`

`api_id` and `api_hash` identify the *application*, not the user account. Every person who runs tgcs should register their own app - sharing credentials violates Telegram's ToS and risks a ban.

These values are **not visible inside the Telegram mobile app** - only on my.telegram.org.

Steps:
1. Open **my.telegram.org** in a browser
2. Log in with your phone number
3. Go to **API development tools**
4. Create an app (name and platform don't matter)
5. Copy `App api_id` (integer) and `App api_hash` (string) into `~/.config/tgcs/config.toml` or you config location


For more information: https://core.telegram.org/api/obtaining_api_id
