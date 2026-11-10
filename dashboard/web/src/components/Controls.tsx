import { useEffect, useState } from "react";
import type { Recording, ReplaySettings, StrategyInfo } from "../types";
import type { Status } from "../useReplay";

interface Props {
  status: Status;
  onStart: (settings: ReplaySettings) => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  onSpeed: (speed: number) => void;
}

/** Picks a recording, a strategy and settings, and starts or controls the replay. */
export function Controls({ status, onStart, onStop, onPause, onResume, onSpeed }: Props) {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [settings, setSettings] = useState<ReplaySettings>({
    recording: "",
    strategy: "v2",
    speed: 20,
    size_btc: 0.001,
    latency_ms: 10,
    maker_fee_bps: 0,
    taker_fee_bps: 0,
  });

  useEffect(() => {
    fetch("/api/recordings")
      .then((r) => r.json())
      .then((list: Recording[]) => {
        setRecordings(list);
        const first = list.find((r) => r.has_trades) ?? list[0];
        if (first) setSettings((s) => ({ ...s, recording: s.recording || first.name }));
      })
      .catch(() => setRecordings([]));
    fetch("/api/strategies")
      .then((r) => r.json())
      .then(setStrategies)
      .catch(() => setStrategies([]));
  }, []);

  const update = <K extends keyof ReplaySettings>(key: K, value: ReplaySettings[K]) =>
    setSettings((s) => ({ ...s, [key]: value }));

  const active = status === "running" || status === "paused" || status === "connecting";
  const description = strategies.find((s) => s.key === settings.strategy)?.description;

  return (
    <section className="panel controls">
      <label>
        Recording
        <select
          value={settings.recording}
          disabled={active}
          onChange={(e) => update("recording", e.target.value)}
        >
          {recordings.map((r) => (
            <option key={r.name} value={r.name}>
              {r.name} ({r.minutes} min{r.has_trades ? "" : ", no trades"})
            </option>
          ))}
        </select>
      </label>
      <label>
        Strategy
        <select
          value={settings.strategy}
          disabled={active}
          onChange={(e) => update("strategy", e.target.value)}
        >
          {strategies.map((s) => (
            <option key={s.key} value={s.key}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Speed {settings.speed}x
        <input
          type="range"
          min={1}
          max={200}
          value={settings.speed}
          onChange={(e) => {
            const speed = Number(e.target.value);
            update("speed", speed);
            onSpeed(speed);
          }}
        />
      </label>
      <label>
        Maker fee (bps)
        <input
          type="number"
          min={0}
          value={settings.maker_fee_bps}
          disabled={active}
          onChange={(e) => update("maker_fee_bps", Number(e.target.value))}
        />
      </label>
      <label>
        Latency (ms)
        <input
          type="number"
          min={0}
          value={settings.latency_ms}
          disabled={active}
          onChange={(e) => update("latency_ms", Number(e.target.value))}
        />
      </label>
      <div className="buttons">
        {!active && (
          <button disabled={!settings.recording} onClick={() => onStart(settings)}>
            Start
          </button>
        )}
        {status === "running" && <button onClick={onPause}>Pause</button>}
        {status === "paused" && <button onClick={onResume}>Resume</button>}
        {active && <button onClick={onStop}>Stop</button>}
      </div>
      {description && <p className="hint">{description}</p>}
    </section>
  );
}
