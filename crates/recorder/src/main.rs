//! Records Coinbase's live level2 (order book) feed to disk, exactly as received.
//!
//! Usage, from the repo root:
//!
//! ```text
//! cargo run --release -p lobster-recorder -- [PRODUCT] [DATA_DIR]
//! cargo run --release -p lobster-recorder -- BTC-USD data
//! ```
//!
//! Each connection writes a new file, `DATA_DIR/coinbase/PRODUCT/<start time>.jsonl`.
//! Every line is `{"recv_ns": <our receive time>, "msg": <Coinbase's message, untouched>}`.
//! Each file starts with a full book snapshot, so it can be replayed on its own.
//! Stop with Ctrl+C.

mod sequence;

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use tokio::fs::{self, File};
use tokio::io::{AsyncWriteExt, BufWriter};
use tokio::sync::watch;
use tokio_tungstenite::{connect_async, tungstenite::Message};

use sequence::{SequenceCheck, SequenceTracker};

/// Coinbase's public market data endpoint. No API key needed :)
const URL: &str = "wss://advanced-trade-ws.coinbase.com";

/// Wait times between reconnect attempts: start small, double each time, cap here.
const MIN_BACKOFF: Duration = Duration::from_secs(1);
const MAX_BACKOFF: Duration = Duration::from_secs(30);

/// A connection that stayed up this long counts as healthy, which resets the backoff.
const HEALTHY_SESSION: Duration = Duration::from_secs(60);

/// How often to print progress, in messages.
const PROGRESS_EVERY: u64 = 10_000;

/// Any error, boxed. Good enough for a program (as opposed to a library).
type Error = Box<dyn std::error::Error + Send + Sync>;

/// Why a recording session ended.
enum Outcome {
    /// The user pressed Ctrl+C.
    Shutdown,
    /// Something went wrong with the connection or the data; start a new session.
    Reconnect(String),
}

#[tokio::main]
async fn main() {
    let mut args = std::env::args().skip(1);
    let product = args.next().unwrap_or_else(|| "BTC-USD".to_string());
    let data_dir = PathBuf::from(args.next().unwrap_or_else(|| "data".to_string()));
    let out_dir = data_dir.join("coinbase").join(&product);

    // Ctrl+C flips this to `true`; every wait below also watches it
    let (shutdown_tx, shutdown) = watch::channel(false);
    tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        let _ = shutdown_tx.send(true);
    });

    let mut backoff = MIN_BACKOFF;
    loop {
        let started = Instant::now();
        let reason = match record_session(&product, &out_dir, shutdown.clone()).await {
            Ok(Outcome::Shutdown) => {
                eprintln!("stopped");
                return;
            }
            Ok(Outcome::Reconnect(reason)) => reason,
            Err(error) => format!("error: {error}"),
        };

        if started.elapsed() >= HEALTHY_SESSION {
            backoff = MIN_BACKOFF;
        }
        eprintln!("session ended ({reason}); reconnecting in {backoff:?}");

        let mut shutdown = shutdown.clone();
        tokio::select! {
            _ = tokio::time::sleep(backoff) => {}
            _ = shutdown.changed() => {
                eprintln!("stopped");
                return;
            }
        }
        backoff = (backoff * 2).min(MAX_BACKOFF);
    }
}

/// One connection: subscribe, then write every message to a new file until
/// the connection drops, a message is missed, or the user presses Ctrl+C.
async fn record_session(
    product: &str,
    out_dir: &Path,
    mut shutdown: watch::Receiver<bool>,
) -> Result<Outcome, Error> {
    if *shutdown.borrow() {
        return Ok(Outcome::Shutdown);
    }

    let (mut ws, _response) = tokio::select! {
        result = connect_async(URL) => result?,
        _ = shutdown.changed() => return Ok(Outcome::Shutdown),
    };
    let subscriptions = [
        json!({ "type": "subscribe", "product_ids": [product], "channel": "level2" }),
        // Without heartbeats, Coinbase closes quiet connections after 60-90 seconds
        json!({ "type": "subscribe", "channel": "heartbeats" }),
    ];
    for subscription in subscriptions {
        ws.send(Message::text(subscription.to_string())).await?;
    }

    fs::create_dir_all(out_dir).await?;
    let path = out_dir.join(format!("{}.jsonl", unix_nanos()));
    let mut out = BufWriter::new(File::create(&path).await?);
    eprintln!("connected; recording {product} to {}", path.display());

    let mut sequence = SequenceTracker::default();
    let mut count: u64 = 0;

    let outcome = loop {
        let message = tokio::select! {
            message = ws.next() => message,
            _ = shutdown.changed() => break Outcome::Shutdown,
        };

        let text = match message {
            Some(Ok(Message::Text(text))) => text,
            Some(Ok(Message::Close(frame))) => {
                break Outcome::Reconnect(format!("server closed the connection: {frame:?}"));
            }
            // Pings and pongs are answered automatically; nothing else is expected
            Some(Ok(_)) => continue,
            Some(Err(error)) => break Outcome::Reconnect(format!("read error: {error}")),
            None => break Outcome::Reconnect("connection ended".to_string()),
        };
        let text = text.as_str();

        // Save first, untouched, so nothing is lost even if the checks below fail
        let line = format!("{{\"recv_ns\":{},\"msg\":{}}}\n", unix_nanos(), text);
        out.write_all(line.as_bytes()).await?;
        count += 1;

        let value: Value = match serde_json::from_str(text) {
            Ok(value) => value,
            Err(error) => break Outcome::Reconnect(format!("unreadable message: {error}")),
        };
        if value.get("type").and_then(Value::as_str) == Some("error") {
            break Outcome::Reconnect(format!("Coinbase sent an error: {text}"));
        }

        if let Some(number) = value.get("sequence_num").and_then(Value::as_u64)
            && let SequenceCheck::Gap { expected, got } = sequence.observe(number)
        {
            // Our copy of the book is now wrong; a new connection starts with a fresh snapshot
            break Outcome::Reconnect(format!("missed messages: expected {expected}, got {got}"));
        }

        // Heartbeats arrive every second, which makes them a good time to flush to disk
        if value.get("channel").and_then(Value::as_str) == Some("heartbeats") {
            out.flush().await?;
        }

        if count.is_multiple_of(PROGRESS_EVERY) {
            eprintln!("{count} messages recorded");
        }
    };

    out.flush().await?;
    eprintln!("wrote {count} messages to {}", path.display());
    Ok(outcome)
}

/// The current time as nanoseconds since 1970 (Unix time).
fn unix_nanos() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or(0)
}
