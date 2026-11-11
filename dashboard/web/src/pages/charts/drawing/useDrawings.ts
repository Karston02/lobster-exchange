import { useCallback, useEffect, useState } from "react";
import { getJson, sendJson } from "../../../api";
import type { Drawing } from "./types";

export interface Drawings {
  list: Drawing[];
  save(drawing: Drawing): void; // create or move
  remove(id: string): void;
}

/** The drawings on one symbol's chart, loaded from and saved to the server.
 *  Changes show at once; the save happens in the background. */
export function useDrawings(symbol: string): Drawings {
  const [list, setList] = useState<Drawing[]>([]);

  useEffect(() => {
    let cancelled = false;
    setList([]);
    getJson<{ drawings: Drawing[] }>(`/api/drawings?symbol=${encodeURIComponent(symbol)}`)
      .then((data) => !cancelled && setList(data.drawings))
      .catch((error) => console.error("couldn't load drawings:", error));
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const save = useCallback((drawing: Drawing) => {
    setList((old) => [...old.filter((d) => d.id !== drawing.id), drawing]);
    sendJson("PUT", `/api/drawings/${drawing.id}`, drawing).catch((error) => console.error("couldn't save drawing:", error));
  }, []);

  const remove = useCallback((id: string) => {
    setList((old) => old.filter((d) => d.id !== id));
    sendJson("DELETE", `/api/drawings/${id}`).catch((error) => console.error("couldn't delete drawing:", error));
  }, []);

  return { list, save, remove };
}
