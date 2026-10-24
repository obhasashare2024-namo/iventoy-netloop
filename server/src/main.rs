// Pure Rust Stateless HTTP 206 Byte-Range Server for iventoy-netloop
use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader, Read, Seek, SeekFrom, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};

fn parse_range(header_val: &str, file_len: u64) -> Option<(u64, u64)> {
    let s = header_val.trim();
    if !s.starts_with("bytes=") {
        return None;
    }
    let spec = &s[6..];
    let parts: Vec<&str> = spec.split('-').collect();
    if parts.len() != 2 {
        return None;
    }
    let start_str = parts[0].trim();
    let end_str = parts[1].trim();

    if start_str.is_empty() {
        // Suffix range: -N
        let suffix_len: u64 = end_str.parse().ok()?;
        let start = file_len.saturating_sub(suffix_len);
        Some((start, file_len.saturating_sub(1)))
    } else {
        let start: u64 = start_str.parse().ok()?;
        if start >= file_len {
            return None;
        }
        let end: u64 = if end_str.is_empty() {
            file_len - 1
        } else {
            let e: u64 = end_str.parse().ok()?;
            e.min(file_len - 1)
        };
        if start > end {
            return None;
        }
        Some((start, end))
    }
}

fn handle_client(mut stream: TcpStream, root_dir: &Path) -> std::io::Result<()> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut req_line = String::new();
    if reader.read_line(&mut req_line)? == 0 {
        return Ok(());
    }

    let req_parts: Vec<&str> = req_line.split_whitespace().collect();
    if req_parts.len() < 2 {
        return Ok(());
    }
    let method = req_parts[0];
    let mut raw_path = req_parts[1];

    if let Some(pos) = raw_path.find('?') {
        raw_path = &raw_path[..pos];
    }

    let mut range_header = None;
    let mut line = String::new();
    while reader.read_line(&mut line)? > 0 {
        if line == "\r\n" || line == "\n" {
            break;
        }
        let lower = line.to_ascii_lowercase();
        if lower.starts_with("range:") {
            if let Some(colon) = line.find(':') {
                range_header = Some(line[colon + 1..].trim().to_string());
            }
        }
        line.clear();
    }

    let decoded_path = raw_path.trim_start_matches('/');
    let target_path = root_dir.join(decoded_path);

    // Canonicalize to prevent directory traversal
    let canonical = match target_path.canonicalize() {
        Ok(c) => c,
        Err(_) => {
            let resp = "HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot Found";
            let _ = stream.write_all(resp.as_bytes());
            return Ok(());
        }
    };

    if !canonical.starts_with(root_dir) || !canonical.is_file() {
        let resp = "HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot Found";
        let _ = stream.write_all(resp.as_bytes());
        return Ok(());
    }

    let mut file = match File::open(&canonical) {
        Ok(f) => f,
        Err(_) => {
            let resp = "HTTP/1.1 403 Forbidden\r\nContent-Length: 9\r\nConnection: close\r\n\r\nForbidden";
            let _ = stream.write_all(resp.as_bytes());
            return Ok(());
        }
    };

    let file_len = match file.metadata() {
        Ok(m) => m.len(),
        Err(_) => 0,
    };

    if let Some(ref r_str) = range_header {
        if let Some((start, end)) = parse_range(r_str, file_len) {
            let chunk_len = end - start + 1;
            let header = format!(
                "HTTP/1.1 206 Partial Content\r\n\
                 Accept-Ranges: bytes\r\n\
                 Content-Range: bytes {}-{}/{}\r\n\
                 Content-Length: {}\r\n\
                 Content-Type: application/octet-stream\r\n\
                 Connection: keep-alive\r\n\r\n",
                start, end, file_len, chunk_len
            );
            stream.write_all(header.as_bytes())?;

            if method != "HEAD" {
                file.seek(SeekFrom::Start(start))?;
                let mut remaining = chunk_len;
                let mut buf = [0u8; 65536];
                while remaining > 0 {
                    let to_read = remaining.min(buf.len() as u64) as usize;
                    let n = file.read(&mut buf[..to_read])?;
                    if n == 0 {
                        break;
                    }
                    stream.write_all(&buf[..n])?;
                    remaining -= n as u64;
                }
            }
            return Ok(());
        } else {
            let resp = format!(
                "HTTP/1.1 416 Range Not Satisfiable\r\nContent-Range: bytes */{}\r\nContent-Length: 0\r\n\r\n",
                file_len
            );
            stream.write_all(resp.as_bytes())?;
            return Ok(());
        }
    }

    // Full 200 OK response
    let header = format!(
        "HTTP/1.1 200 OK\r\n\
         Accept-Ranges: bytes\r\n\
         Content-Length: {}\r\n\
         Content-Type: application/octet-stream\r\n\
         Connection: keep-alive\r\n\r\n",
        file_len
    );
    stream.write_all(header.as_bytes())?;

    if method != "HEAD" {
        let mut buf = [0u8; 65536];
        loop {
            let n = file.read(&mut buf)?;
            if n == 0 {
                break;
            }
            stream.write_all(&buf[..n])?;
        }
    }

    Ok(())
}

fn main() -> std::io::Result<()> {
    let args: Vec<String> = env::args().collect();
    let port = env::var("PORT").unwrap_or_else(|_| "26001".to_string());
    let dir = if args.len() > 1 {
        PathBuf::from(&args[1])
    } else {
        env::current_dir()?
    };
    let canonical_root = dir.canonicalize()?;

    let bind_addr = format!("0.0.0.0:{}", port);
    let listener = TcpListener::bind(&bind_addr)?;
    println!("[NetLoop-HTTP] Pure Rust HTTP 206 server listening on {}", bind_addr);
    println!("[NetLoop-HTTP] Serving directory: {}", canonical_root.display());

    for stream in listener.incoming() {
        if let Ok(stream) = stream {
            let root = canonical_root.clone();
            std::thread::spawn(move || {
                let _ = handle_client(stream, &root);
            });
        }
    }
    Ok(())
}
