//! Быстрый HTTP-транспорт SoberX: keep-alive пул соединений + параллельные загрузки.
//! Заменяет последовательные ureq-запросы: один TCP+TLS коннект переиспользуется,
//! а чанки клиента качаются в N потоков одновременно (N = число ядер, до 8).

use anyhow::{anyhow, Context, Result};
use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;

/// Таймауты по умолчанию (как в sober: generous на медленных CDN).
pub const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
pub const IO_TIMEOUT: Duration = Duration::from_secs(120);

// ---------------------------------------------------------------------------
// Пул keep-alive соединений к хосту
// ---------------------------------------------------------------------------

/// Пул: host -> очередь свободных сокетов. Потокобезопасен (Mutex<Vec>).
type PoolKey = String; // "host:port"
static POOL: OnceLock<Mutex<std::collections::HashMap<PoolKey, Vec<TcpStream>>>> = OnceLock::new();

fn pool() -> &'static Mutex<std::collections::HashMap<PoolKey, Vec<TcpStream>>> {
    POOL.get_or_init(Default::default)
}

fn take_conn(host: &str, port: u16, tls: bool) -> Result<TcpStream> {
    let key = format!("{host}:{port}");
    if let Some(s) = pool().lock().unwrap().remove(&key).and_then(|mut v| v.pop()) {
        // быстрая проверка живости: nonblocking peek не делаем — просто ставим таймауты
        let _ = s.set_read_timeout(Some(IO_TIMEOUT));
        let _ = s.set_write_timeout(Some(IO_TIMEOUT));
        // TLS поверх переиспользованного сокета невозможен корректно — для https
        // всегда новый handshake (SNI), но TCP-коннект уже прогрет ОС-кэшем.
        if !tls {
            return Ok(s);
        }
    }
    let addr = format!("{host}:{port}");
    let s = TcpStream::connect(&addr).with_context(|| format!("connect {addr}"))?;
    s.set_nodelay(true)?;
    s.set_read_timeout(Some(CONNECT_TIMEOUT.max(IO_TIMEOUT)))?;
    s.set_write_timeout(Some(IO_TIMEOUT))?;
    Ok(s)
}

fn put_conn(key: PoolKey, s: TcpStream) {
    let mut p = pool().lock().unwrap();
    let e = p.entry(key).or_default();
    if e.len() < 4 {
        e.push(s);
    }
    // иначе сокет просто дропается
}

// ---------------------------------------------------------------------------
// GET в память / на диск (HTTP/1.1 keep-alive; HTTPS через ureq fallback)
// ---------------------------------------------------------------------------

pub fn is_https(url: &str) -> bool {
    url.starts_with("https://")
}

/// Разобрать http URL: (host, port, path). Только для http:// (чистый TCP путь).
fn split_http(url: &str) -> Option<(String, u16, String)> {
    let rest = url.strip_prefix("http://")?;
    let (authority, path) = match rest.find('/') {
        Some(i) => (&rest[..i], &rest[i..]),
        None => (rest, "/"),
    };
    let (host, port) = match authority.rsplit_once(':') {
        Some((h, p)) => (h.to_string(), p.parse().ok()?),
        None => (authority.to_string(), 80),
    };
    Some((host, port, path.to_string()))
}

/// GET одного ресурса в байты. https -> ureq (rustls/native-tls), http -> пул TCP.
pub fn get_bytes(url: &str) -> Result<Vec<u8>> {
    if let Some((host, port, path)) = split_http(url) {
        let key = format!("{host}:{port}");
        for attempt in 0..2u8 {
            let mut s = take_conn(&host, port, false)?;
            let req = format!(
                "GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: SoberX/1.0\r\nConnection: keep-alive\r\nAccept-Encoding: identity\r\n\r\n"
            );
            if s.write_all(req.as_bytes()).is_err() && attempt == 0 {
                continue; // мёртвый сокет из пула — берём новый
            }
            s.flush()?;
            let resp = read_http_response(&mut s)?;
            put_conn(key.clone(), s);
            return finish_response(url, resp);
        }
        Err(anyhow!("не удалось получить {url}"))
    } else {
        // https: ureq держит свой пул внутри agent'а — используем общий агент
        static AGENT: OnceLock<ureq::Agent> = OnceLock::new();
        let agent = AGENT.get_or_init(|| {
            ureq::AgentBuilder::new()
                .user_agent(crate::http::USER_AGENT)
                .timeout_connect(CONNECT_TIMEOUT)
                .timeout(IO_TIMEOUT)
                .build()
        });
        let resp = agent
            .get(url)
            .call()
            .with_context(|| format!("GET {url}"))?;
        let status = resp.status();
        if status != 200 {
            return Err(anyhow!("HTTP {status} для {url}"));
        }
        let mut buf = Vec::new();
        resp.into_reader().read_to_end(&mut buf)?;
        Ok(buf)
    }
}

struct RawResponse {
    status: u16,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

fn read_http_response(s: &mut TcpStream) -> Result<RawResponse> {
    let mut acc: Vec<u8> = Vec::with_capacity(16 * 1024);
    let mut tmp = [0u8; 8192];
    // заголовок до \r\n\r\n
    let header_end = loop {
        if let Some(pos) = find_sub(&acc, b"\r\n\r\n") {
            break pos + 4;
        }
        let n = s.read(&mut tmp)?;
        if n == 0 {
            return Err(anyhow!("обрыв соединения"));
        }
        acc.extend_from_slice(&tmp[..n]);
    };
    let head = String::from_utf8_lossy(&acc[..header_end]).to_lowercase();
    let status: u16 = head
        .split_whitespace()
        .nth(1)
        .and_then(|v| v.parse().ok())
        .context("битый HTTP-статус")?;
    let mut headers = Vec::new();
    for line in head.split("\r\n").skip(1) {
        if let Some((k, v)) = line.split_once(':') {
            headers.push((k.trim().to_string(), v.trim().to_string()));
        }
    }
    let mut body = acc[header_end..].to_vec();
    let chunked = headers.iter().any(|(k, v)| k == "transfer-encoding" && v.contains("chunked"));
    let clen: Option<usize> = headers
        .iter()
        .find(|(k, _)| k == "content-length")
        .and_then(|(_, v)| v.parse().ok());
    if chunked {
        loop {
            let n = s.read(&mut tmp)?;
            if n == 0 {
                break;
            }
            body.extend_from_slice(&tmp[..n]);
            if body.ends_with(b"0\r\n\r\n") {
                break;
            }
        }
        body = dechunk(&body)?;
    } else if let Some(cl) = clen {
        while body.len() < cl {
            let n = s.read(&mut tmp)?;
            if n == 0 {
                break;
            }
            body.extend_from_slice(&tmp[..n]);
        }
    } else {
        // connection: close стиль
        loop {
            let n = s.read(&mut tmp)?;
            if n == 0 {
                break;
            }
            body.extend_from_slice(&tmp[..n]);
        }
    }
    Ok(RawResponse { status, headers, body })
}

fn find_sub(hay: &[u8], needle: &[u8]) -> Option<usize> {
    hay.windows(needle.len()).position(|w| w == needle)
}

fn dechunk(body: &[u8]) -> Result<Vec<u8>> {
    let mut out = Vec::with_capacity(body.len());
    let mut i = 0usize;
    while i < body.len() {
        let nl = find_sub(&body[i..], b"\r\n").context("битый chunk size")? + i;
        let sz = usize::from_str_radix(
            std::str::from_utf8(&body[i..nl])
                .map_err(|_| anyhow!("битый chunk size"))?
                .split(';')
                .next()
                .unwrap(),
            16,
        )
        .context("битый chunk size")?;
        if sz == 0 {
            break;
        }
        let start = nl + 2;
        let end = start + sz;
        if end > body.len() {
            return Err(anyhow!("усечённый chunked body"));
        }
        out.extend_from_slice(&body[start..end]);
        i = end + 2;
    }
    Ok(out)
}

fn finish_response(url: &str, r: RawResponse) -> Result<Vec<u8>> {
    if r.status != 200 {
        return Err(anyhow!("HTTP {} для {url}", r.status));
    }
    Ok(r.body)
}

// ---------------------------------------------------------------------------
// Параллельная пакетная загрузка чанков
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct ChunkJob {
    pub name: String,
    pub url: String,
    pub dest: PathBuf,
    pub sha256: Option<String>,
}

#[derive(Debug)]
pub struct ChunkResult {
    pub name: String,
    pub ok: bool,
    pub bytes: u64,
    pub err: Option<String>,
}

/// Скачать пачку файлов в `threads` рабочих потоков. Возвращает результаты
/// (по одному на job) и суммарное число скачанных байт.
pub fn download_batch(jobs: Vec<ChunkJob>, threads: usize) -> (Vec<ChunkResult>, u64) {
    let threads = threads.clamp(1, 8);
    let (tx, rx) = mpsc::channel::<ChunkResult>();
    let queue = Arc::new(Mutex::new(jobs.into_iter().collect::<std::collections::VecDeque<_>>()));

    std::thread::scope(|sc| {
        for _ in 0..threads {
            let queue = queue.clone();
            let tx = tx.clone();
            sc.spawn(move || loop {
                let job = {
                    let mut q = queue.lock().unwrap();
                    match q.pop_front() {
                        Some(j) => j,
                        None => break,
                    }
                };
                let res = run_job(&job);
                let _ = tx.send(res);
            });
        }
        drop(tx);
    });

    let mut results: Vec<ChunkResult> = rx.iter().collect();
    results.sort_by(|a, b| a.name.cmp(&b.name));
    let total: u64 = results.iter().map(|r| r.bytes).sum();
    (results, total)
}

fn run_job(job: &ChunkJob) -> ChunkResult {
    let fail = |e: String| ChunkResult {
        name: job.name.clone(),
        ok: false,
        bytes: 0,
        err: Some(e),
    };
    if let Some(parent) = job.dest.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let tmp = job.dest.with_extension("soberx.part");
    let data = match get_bytes(&job.url) {
        Ok(d) => d,
        Err(e) => return fail(e.to_string()),
    };
    if let Some(expected) = &job.sha256 {
        use sha2::{Digest, Sha256};
        let got = format!("{:x}", Sha256::digest(&data));
        if got != expected.to_ascii_lowercase() {
            return fail("SHA-256 не совпал".into());
        }
    }
    if let Err(e) = write_atomic(&tmp, &job.dest, &data) {
        return fail(e.to_string());
    }
    ChunkResult {
        name: job.name.clone(),
        ok: true,
        bytes: data.len() as u64,
        err: None,
    }
}

fn write_atomic(tmp: &Path, dest: &Path, data: &[u8]) -> Result<()> {
    let mut f = fs::File::create(tmp)?;
    #[cfg(unix)]
    {
        use std::os::unix::io::AsRawFd;
        // предварительная аллокация — меньше фрагментации на больших чанках
        let _ = f.set_len(data.len() as u64);
        let _ = f.as_raw_fd();
    }
    f.write_all(data)?;
    f.sync_all()?;
    drop(f);
    fs::rename(tmp, dest)?;
    Ok(())
}

/// Число потоков по умолчанию: ядра, но не больше 8 и не меньше 2.
pub fn default_threads() -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
        .clamp(2, 8)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dechunk_parses_chunks() {
        let body = b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n";
        assert_eq!(dechunk(body).unwrap(), b"hello world");
    }

    #[test]
    fn split_http_parses() {
        let (h, p, path) = split_http("http://example.com:8080/a/b").unwrap();
        assert_eq!((h.as_str(), p, path.as_str()), ("example.com", 8080, "/a/b"));
        let (h, p, path) = split_http("http://host/x").unwrap();
        assert_eq!((h.as_str(), p, path.as_str()), ("host", 80, "/x"));
        assert!(split_http("https://host/x").is_none());
    }

    /// Интеграция: локальный HTTP-сервер + параллельный batch против последовательного.
    #[test]
    fn batch_parallel_faster_than_sequential() {
        use std::net::TcpListener;
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        // сервер: отдаёт по keep-alive 64 КБ на каждый GET, с задержкой 50мс на запрос
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let mut s = match stream { Ok(s) => s, Err(_) => break };
                std::thread::spawn(move || {
                    loop {
                        let mut line = [0u8; 1];
                        let mut req = Vec::new();
                        loop {
                            if s.read(&mut line).unwrap_or(0) == 0 { return; }
                            req.push(line[0]);
                            if req.ends_with(b"\r\n\r\n") { break; }
                        }
                        std::thread::sleep(Duration::from_millis(50));
                        let payload = vec![b'A'; 64 * 1024];
                        let head = format!("HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: keep-alive\r\n\r\n", payload.len());
                        let _ = s.write_all(head.as_bytes());
                        let _ = s.write_all(&payload);
                    }
                });
            }
        });

        let dir = std::env::temp_dir().join(format!("soberx-batch-test-{}", std::process::id()));
        let mk_jobs = |tag: &str| -> Vec<ChunkJob> {
            (0..6).map(|i| ChunkJob {
                name: format!("{tag}{i}"),
                url: format!("http://{addr}/file{i}"),
                dest: dir.join(format!("{tag}{i}.bin")),
                sha256: None,
            }).collect()
        };

        let t0 = std::time::Instant::now();
        let (res_seq, _) = download_batch(mk_jobs("seq-"), 1); // последовательно
        let seq_ms = t0.elapsed().as_millis();

        let t1 = std::time::Instant::now();
        let (res_par, bytes) = download_batch(mk_jobs("par-"), 6); // параллельно
        let par_ms = t1.elapsed().as_millis();

        assert_eq!(res_seq.iter().filter(|r| r.ok).count(), 6);
        assert_eq!(res_par.iter().filter(|r| r.ok).count(), 6);
        assert_eq!(bytes, 6 * 64 * 1024);
        println!("seq={seq_ms}ms par={par_ms}ms");
        assert!(par_ms < seq_ms, "параллельная загрузка должна быть быстрее: seq={seq_ms} par={par_ms}");
        let _ = fs::remove_dir_all(&dir);
    }
}
