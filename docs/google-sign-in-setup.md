# Google sign-in connection

Status, 2 November 2026: The user's Google OAuth client ID is configured in the ignored root `.env`. The running API exposes that same ID, the frontend renders the Google-provided "Continue with Google" button, and no browser warning/error was reported during rendering. API health confirms MongoDB is reachable. A real Google sign-in completed successfully: the app displayed the signed-in dashboard, and Atlas contains a recent Google user login and an active Google session. Logout/re-login and two-account isolation have not been exercised live.

## Intended client

- Application: SpendSense AI
- OAuth client type: Web application
- Authorized JavaScript origins: `http://localhost` and `http://localhost:5173`
- Sign-in method: Google Identity Services button, popup/callback returning an ID token
- Redirect URI: not used by the current JavaScript callback flow
- Requested identity: Google subject ID, name and verified email; no Drive/Gmail data access
- Server setting: `GOOGLE_CLIENT_ID` in ignored `.env`
- Client secret: not needed by this flow and must not be added to frontend code

The API, frontend and extraction worker have been started with the current configuration. The real Google callback has been verified at `http://localhost:5173`. Development accounts remain enabled for local testing. Keep the app on the exact configured origin. If Google reports an origin or audience restriction, check the client's authorized origins and the project's audience/test users. [Google's official setup instructions](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid) describe client creation and localhost origins.

## Verification before declaring it connected

1. Confirm the configured Google button loads without an origin/client error.
2. Sign in with the user's real Google account; verify the backend creates a `google:<sub>` identity and server-side session in Atlas.
3. Confirm the account sees only its own receipts, expenses and previews. Development identities are separate and are not silently merged with Google accounts.
4. Verify logout and a new sign-in. Disable development identities once real Google access has been verified if the user wants Google-only login.

The backend already verifies Google ID-token signatures/audience through `google-auth`, requires a verified email and the browser's nonce, checks Origin/CSRF, and uses the verified subject as the ownership key. A new local-MongoDB integration test verifies failed verifier responses, nonce mismatch, unverified email, correct audience forwarding, replacement of a development session and isolation between two Google identities. Five integration tests pass. The Google verifier is mocked in that test; it is not evidence of a successful live Google login.
