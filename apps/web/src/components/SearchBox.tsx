"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { ObjectSummary } from "@atlas/shared-types";
import { api, ApiError } from "@/lib/api";

interface Props {
  label: string;
  onSelect: (o: ObjectSummary) => void;
  testId: string;
}

/** Keyboard-accessible combobox: type, ArrowUp/ArrowDown to move, Enter to choose. */
export function SearchBox({ label, onSelect, testId }: Props) {
  const id = useId();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<ObjectSummary[]>([]);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const query = q.trim();
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const mine = ++seq.current;
    const t = setTimeout(() => {
      api
        .search(query)
        .then((r) => {
          if (mine !== seq.current) return;
          setResults(r.results);
          setActive(0);
          setError(null);
        })
        .catch((e: unknown) => {
          if (mine === seq.current) setError(e instanceof ApiError ? e.message : "search failed");
        });
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  function choose(o: ObjectSummary | undefined) {
    if (!o) return;
    onSelect(o);
    setQ("");
    setResults([]);
  }

  return (
    <div className="search">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        data-testid={testId}
        role="combobox"
        aria-expanded={results.length > 0}
        aria-controls={`${id}-list`}
        aria-activedescendant={results[active] ? `${id}-opt-${active}` : undefined}
        autoComplete="off"
        placeholder="e.g. Proxima Centauri, Sun, Barnard"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(results[active]);
          } else if (e.key === "Escape") {
            setResults([]);
          }
        }}
      />
      {error && <p className="bad" role="alert">{error}</p>}
      {results.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="results">
          {results.map((r, i) => (
            <li
              key={r.id}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : undefined}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(r);
              }}
            >
              <span>{r.display_name}</span>{" "}
              <small>
                {r.object_type}
                {r.has_3d_position ? "" : " · sky only"}
                {r.matched_alias && r.matched_alias !== r.display_name ? ` · “${r.matched_alias}”` : ""}
              </small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
