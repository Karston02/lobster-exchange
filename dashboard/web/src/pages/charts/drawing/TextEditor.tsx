import { useEffect, useRef, useState } from "react";
import type { Pixel } from "./geometry";

interface Props {
  at: Pixel;
  initial: string;
  onDone: (text: string | null) => void; // null: cancelled
}

/** A small text box over the chart for writing or editing a text drawing.
 *  Enter or clicking away keeps the words; Esc cancels. */
export function TextEditor({ at, initial, onDone }: Props) {
  const [text, setText] = useState(initial);
  const input = useRef<HTMLInputElement>(null);
  const done = useRef(false); // Enter then blur would otherwise finish twice

  useEffect(() => input.current?.focus(), []);

  const finish = (value: string | null) => {
    if (done.current) return;
    done.current = true;
    onDone(value);
  };

  return (
    <input
      ref={input}
      className="text-editor"
      style={{ left: at.x, top: at.y - 14 }}
      value={text}
      maxLength={200}
      placeholder="Text"
      aria-label="Drawing text"
      onChange={(e) => setText(e.target.value)}
      onKeyDown={(e) => {
        e.stopPropagation(); // keep Delete and Backspace from deleting the drawing
        if (e.key === "Enter") finish(text);
        if (e.key === "Escape") finish(null);
      }}
      onBlur={() => finish(text)}
      onPointerDown={(e) => e.stopPropagation()}
    />
  );
}
