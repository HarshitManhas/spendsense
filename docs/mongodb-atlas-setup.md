# MongoDB Atlas connection

Connected and verified on 2 November 2026. The active application database is Atlas `spendsense` on the existing free `HarshitData` cluster. The paused cluster was resumed. The user created `spendsense_app` with `readWrite @ spendsense`, restricted to that cluster. The existing network access list already permitted the connection and was not changed.

The user chose an empty cloud database: no receipts or files were migrated. The local database still has six active receipts and ten stored GridFS files. Credentials stay in ignored local environment files; they are not included in this document or frontend code.

Verification passed for Atlas DNS/TLS, authentication, index creation, write/read/delete, GridFS byte-for-byte round trip, running API health and worker startup. Temporary probes were removed. Atlas receipt/file counts were both zero after checks. The API and worker were restarted with Atlas settings. Existing local sessions were not migrated, so sign in again after refreshing the app.

The application already uses MongoDB and GridFS. Atlas changes the database address, not the data schema. The setup procedure below is retained for future connections.

1. Sign in to Atlas and select/create the intended project and cluster. Use the Free option if creating a development cluster; do not choose a paid tier without a budget decision.
2. Configure a database user with read/write access to `spendsense`, and permit the application machine's current public IP in the network access list. The database user is separate from the Atlas website login. See [Atlas's official driver connection guide](https://www.mongodb.com/docs/atlas/driver-connection/).
3. Choose Connect → Drivers → Python and copy the `mongodb+srv://` connection string. Fill database credentials locally, with special characters percent-encoded. Keep the completed URI in the ignored `.env.atlas` candidate file, never in frontend code or a tracked document:

```dotenv
MONGODB_URI=mongodb+srv://<database-user>:<encoded-password>@<cluster-host>/?retryWrites=true&w=majority
MONGODB_DATABASE=spendsense
```

Alternatively, retain `<db_password>` in the URI and enter `ATLAS_PASSWORD='your database password'` in this private file. The helper percent-encodes it automatically and disables variable interpolation while reading credentials. Never send the value in chat.

4. Verify without replacing the current connection:

```powershell
.venv\Scripts\python.exe scripts/connect_atlas.py
```

The check pings Atlas and verifies index creation/write/read/delete using one disposable connection-check document in `_connection_checks`. It sends no receipt data. A TTL removes a probe if cleanup is interrupted. Errors are sanitized so the URI/password are not printed.

5. After a successful check, switch and restart the API and extraction worker:

```powershell
.venv\Scripts\python.exe scripts/connect_atlas.py --apply
```

The helper retains the first pre-Atlas configuration in ignored `.env.before-atlas`. It refuses incomplete credentials or disabled TLS checks and changes `.env` only after verification succeeds.

Existing local receipts and GridFS files are **not** copied automatically. Decide whether to start with an empty Atlas database or migrate existing data before switching. A migration must preserve receipt IDs, file IDs, ownership and file bytes; active local sessions should not be copied. Keep the local database as a rollback copy until the Atlas app workflow has been verified.
