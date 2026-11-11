import { useCallback, useEffect, useRef, useState } from "react";
import { getJson, sendJson } from "../../../api";
import type { Drawing } from "./types";

/** One change, as the drawing before and after (null: didn't exist / deleted). */
interface Change {
  id: string;
  before: Drawing | null;
  after: Drawing | null;
}

export interface Drawings {
  list: Drawing[];
  save(drawing: Drawing): void; // create, move, edit, lock
  remove(id: string): void;
  undo(): void;
  redo(): void;
  canUndo: boolean;
  canRedo: boolean;
}

/** The drawings on one symbol's chart, loaded from and saved to the server, with undo and redo.
 *  Changes show at once; the save happens in the background. History is per symbol, for this visit. */
export function useDrawings(symbol: string): Drawings {
  const [list, setList] = useState<Drawing[]>([]);
  const current = useRef<Drawing[]>([]); // the same list, readable inside callbacks
  const undos = useRef<Change[]>([]);
  const redos = useRef<Change[]>([]);
  const [, setVersion] = useState(0); // bump to re-render when the history changes

  const replace = useCallback((next: Drawing[]) => {
    current.current = next;
    setList(next);
  }, []);

  useEffect(() => {
    let cancelled = false;
    replace([]);
    undos.current = [];
    redos.current = [];
    getJson<{ drawings: Drawing[] }>(`/api/drawings?symbol=${encodeURIComponent(symbol)}`)
      .then((data) => !cancelled && replace(data.drawings))
      .catch((error) => console.error("couldn't load drawings:", error));
    return () => {
      cancelled = true;
    };
  }, [symbol, replace]);

  /** Makes the drawing `id` look like `drawing` (or removes it), here and on the server. */
  const apply = useCallback(
    (id: string, drawing: Drawing | null) => {
      const others = current.current.filter((d) => d.id !== id);
      if (drawing) {
        replace([...others, drawing]);
        sendJson("PUT", `/api/drawings/${id}`, drawing).catch((e) => console.error("couldn't save drawing:", e));
      } else {
        replace(others);
        sendJson("DELETE", `/api/drawings/${id}`).catch((e) => console.error("couldn't delete drawing:", e));
      }
    },
    [replace],
  );

  const record = useCallback((change: Change) => {
    undos.current.push(change);
    redos.current = []; // a new change ends the old future
    setVersion((v) => v + 1);
  }, []);

  const save = useCallback(
    (drawing: Drawing) => {
      const before = current.current.find((d) => d.id === drawing.id) ?? null;
      record({ id: drawing.id, before, after: drawing });
      apply(drawing.id, drawing);
    },
    [apply, record],
  );

  const remove = useCallback(
    (id: string) => {
      const before = current.current.find((d) => d.id === id);
      if (!before) return;
      record({ id, before, after: null });
      apply(id, null);
    },
    [apply, record],
  );

  const undo = useCallback(() => {
    const change = undos.current.pop();
    if (!change) return;
    redos.current.push(change);
    apply(change.id, change.before);
    setVersion((v) => v + 1);
  }, [apply]);

  const redo = useCallback(() => {
    const change = redos.current.pop();
    if (!change) return;
    undos.current.push(change);
    apply(change.id, change.after);
    setVersion((v) => v + 1);
  }, [apply]);

  return { list, save, remove, undo, redo, canUndo: undos.current.length > 0, canRedo: redos.current.length > 0 };
}
