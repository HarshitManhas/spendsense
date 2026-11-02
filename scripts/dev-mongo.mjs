import { MongoMemoryServer } from 'mongodb-memory-server-core';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const dbPath = resolve('.local-db');
await mkdir(dbPath, { recursive: true });
// A real mongod with persistent WiredTiger files, bound only to loopback.
const server = await MongoMemoryServer.create({
  binary: { version: '8.0.17' },
  instance: { dbPath, port: 27017, ip: '127.0.0.1', storageEngine: 'wiredTiger' },
});
console.log(`MongoDB ready: ${server.getUri()} (data: ${dbPath})`);
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => {
  await server.stop({ doCleanup: false });
  process.exit(0);
});
