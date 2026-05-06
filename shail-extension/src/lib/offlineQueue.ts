/**
 * Offline-capture queue backed by IndexedDB.
 *
 * When the SHAIL backend is offline, content scripts still emit
 * CaptureCandidate payloads. We persist them here so that captures are
 * not lost across browser restarts. The background script drains the
 * queue once `/health` returns 200.
 */

import type { CaptureCandidate } from '../types/contracts';

const DB_NAME    = 'shail-extension';
const DB_VERSION = 1;
const STORE      = 'capture_queue';
const MAX_ITEMS  = 500;

interface QueueRow {
  id: number;
  payload: CaptureCandidate;
  enqueued_at: number;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
}

export async function enqueue(payload: CaptureCandidate): Promise<void> {
  const db = await openDB();
  await new Promise<void>((resolve, reject) => {
    const tx    = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    store.add({ payload, enqueued_at: Date.now() });
    tx.oncomplete = () => resolve();
    tx.onerror    = () => reject(tx.error);
  });
  // Trim if oversized — keep newest MAX_ITEMS
  await trimIfNeeded(db);
}

export async function size(): Promise<number> {
  const db = await openDB();
  return new Promise<number>((resolve, reject) => {
    const tx    = db.transaction(STORE, 'readonly');
    const store = tx.objectStore(STORE);
    const req   = store.count();
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
}

/**
 * Drain queued captures by invoking `send` for each, in FIFO order.
 * Stops on the first send that throws — items not yet drained stay queued.
 * Returns the number of items successfully drained.
 */
export async function drain(
  send: (payload: CaptureCandidate) => Promise<void>,
  batchLimit = 50,
): Promise<number> {
  const db = await openDB();
  const rows: QueueRow[] = await new Promise((resolve, reject) => {
    const tx    = db.transaction(STORE, 'readonly');
    const store = tx.objectStore(STORE);
    const req   = store.getAll(undefined, batchLimit);
    req.onsuccess = () => resolve(req.result as QueueRow[]);
    req.onerror   = () => reject(req.error);
  });

  let drained = 0;
  for (const row of rows) {
    try {
      await send(row.payload);
    } catch {
      break;  // Backend went offline mid-drain; leave the rest queued.
    }
    await new Promise<void>((resolve, reject) => {
      const tx    = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(row.id);
      tx.oncomplete = () => resolve();
      tx.onerror    = () => reject(tx.error);
    });
    drained++;
  }
  return drained;
}

async function trimIfNeeded(db: IDBDatabase): Promise<void> {
  const count = await new Promise<number>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const r  = tx.objectStore(STORE).count();
    r.onsuccess = () => resolve(r.result);
    r.onerror   = () => reject(r.error);
  });
  if (count <= MAX_ITEMS) return;
  // Drop the oldest (count - MAX_ITEMS) rows
  const toDrop = count - MAX_ITEMS;
  const ids: number[] = await new Promise((resolve, reject) => {
    const tx    = db.transaction(STORE, 'readonly');
    const store = tx.objectStore(STORE);
    const req   = store.getAllKeys(undefined, toDrop);
    req.onsuccess = () => resolve(req.result as number[]);
    req.onerror   = () => reject(req.error);
  });
  await new Promise<void>((resolve, reject) => {
    const tx    = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    ids.forEach((id) => store.delete(id));
    tx.oncomplete = () => resolve();
    tx.onerror    = () => reject(tx.error);
  });
}
