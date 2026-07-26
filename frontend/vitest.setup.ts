// Guarantee a working `localStorage` in tests.
//
// jsdom provides one, but Node >= 22 ships its own experimental `localStorage`
// global that is `undefined` unless the process was started with
// `--localstorage-file`. That built-in shadows jsdom's, so `localStorage` reads
// as undefined inside tests and anything persisting state throws. Installing an
// in-memory Storage when the environment's is unusable keeps tests independent
// of the host Node version.

class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.store.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  if (typeof globalThis[name]?.setItem !== "function") {
    Object.defineProperty(globalThis, name, {
      value: new MemoryStorage(),
      configurable: true,
      writable: true,
    });
  }
}
