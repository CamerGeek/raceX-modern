"use client";

type OfflineRecord<T> = {
  key: string;
  savedAt: number;
  payload: T;
};

const DATABASE_NAME = "racex-offline";
const STORE_NAME = "entries";
const DATABASE_VERSION = 1;

let databasePromise: Promise<IDBDatabase | null> | null = null;

function openDatabase(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  if (!databasePromise) {
    databasePromise = new Promise((resolve) => {
      const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(STORE_NAME)) {
          database.createObjectStore(STORE_NAME, { keyPath: "key" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
      request.onblocked = () => resolve(null);
    });
  }
  return databasePromise;
}

export async function saveOffline<T>(key: string, payload: T): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  await new Promise<void>((resolve) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put({ key, savedAt: Date.now(), payload } satisfies OfflineRecord<T>);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => resolve();
    transaction.onabort = () => resolve();
  });
}

export async function readOffline<T>(key: string): Promise<{ payload: T; savedAt: number } | null> {
  const database = await openDatabase();
  if (!database) return null;
  return await new Promise((resolve) => {
    const transaction = database.transaction(STORE_NAME, "readonly");
    const request = transaction.objectStore(STORE_NAME).get(key);
    request.onsuccess = () => {
      const record = request.result as OfflineRecord<T> | undefined;
      resolve(record ? { payload: record.payload, savedAt: record.savedAt } : null);
    };
    request.onerror = () => resolve(null);
  });
}

async function deleteKeys(match: (key: string) => boolean): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  await new Promise<void>((resolve) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.openCursor();
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      if (match(String(cursor.key))) cursor.delete();
      cursor.continue();
    };
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => resolve();
    transaction.onabort = () => resolve();
  });
}

export function removeOfflineKeys(prefixes: string[]) {
  return deleteKeys((key) => prefixes.some((prefix) => key.startsWith(prefix)));
}

export const offlineKeys = {
  analysis: (userId: string, date: string) => `analysis:${userId}:${date}`,
  analysisPrefix: (userId: string) => `analysis:${userId}:`,
  profile: (userId: string) => `profile:${userId}`,
  lastProfile: "last-profile",
  odds: (date: string) => `odds:${date}`,
  topEight: (date: string) => `top-eight:${date}`,
};
