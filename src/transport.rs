//! Synchronous WebSocket transport. TLS verification stays enabled, including
//! when connecting through the managed cloud's HTTP CONNECT proxy.

use std::collections::BTreeMap;
use std::env;
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail, ensure};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use native_tls::TlsConnector;
use percent_encoding::percent_decode_str;
use tungstenite::client::{IntoClientRequest, client_with_config};
use tungstenite::handshake::HandshakeError;
use tungstenite::http::HeaderMap;
use tungstenite::protocol::WebSocketConfig;
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{Error, WebSocket};
use url::Url;

use crate::event::Event;

pub type Socket = WebSocket<MaybeTlsStream<TcpStream>>;
const MAX_HANDSHAKE_BYTES: usize = 32 * 1024;

#[derive(Debug)]
struct PermanentTransportFailure(String);
impl std::fmt::Display for PermanentTransportFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for PermanentTransportFailure {}

pub(crate) fn is_permanent_failure(error: &anyhow::Error) -> bool {
    error.downcast_ref::<PermanentTransportFailure>().is_some()
}

fn reject_http(status: u16, message: String) -> anyhow::Error {
    if (400..500).contains(&status) && status != 408 && status != 429 {
        PermanentTransportFailure(message).into()
    } else {
        anyhow::anyhow!(message)
    }
}

pub fn connect(
    endpoint: &str,
    timeout: Duration,
    record: &mut (impl FnMut(Event) -> Result<()> + ?Sized),
) -> Result<Socket> {
    let url = Url::parse(endpoint).context("invalid exchange URL")?;
    ensure!(
        url.scheme() == "wss",
        "exchange connections require wss and verified TLS"
    );
    let host = url.host_str().context("exchange URL has no host")?;
    let port = url
        .port_or_known_default()
        .context("exchange URL has no port")?;
    let proxy = configured_proxy(host, port)?;
    let mut tcp = if let Some(proxy) = &proxy {
        connect_tcp(
            proxy.host_str().context("proxy has no hostname")?,
            proxy.port_or_known_default().context("proxy has no port")?,
            timeout,
        )?
    } else {
        connect_tcp(host, port, timeout)?
    };
    record(Event::TcpConnected)?;
    tcp.set_nodelay(true)?;
    tcp.set_read_timeout(Some(timeout))?;
    tcp.set_write_timeout(Some(timeout))?;
    if let Some(proxy) = &proxy {
        establish_tunnel(&mut tcp, host, port, proxy)?;
    }
    // On Linux native-tls uses OpenSSL's trust configuration, including
    // SSL_CERT_FILE/SSL_CERT_DIR; never disable peer or hostname verification.
    let tls = TlsConnector::new()?
        .connect(host, tcp)
        .context("verified TLS handshake failed")?;
    let stream = MaybeTlsStream::NativeTls(tls);
    let request = endpoint.into_client_request()?;
    record(Event::UpgradeRequest {
        method: request.method().to_string(),
        uri: request.uri().to_string(),
        headers: public_headers(request.headers()),
    })?;
    let config = WebSocketConfig::default()
        .max_message_size(Some(1024 * 1024))
        .max_frame_size(Some(1024 * 1024));
    match client_with_config(request, stream, Some(config)) {
        Ok((socket, response)) => {
            record(Event::UpgradeResponse {
                status: response.status().as_u16(),
                headers: public_headers(response.headers()),
            })?;
            set_io_timeout(&socket, Duration::from_millis(250))?;
            Ok(socket)
        }
        Err(HandshakeError::Failure(Error::Http(response))) => {
            record(Event::UpgradeResponse {
                status: response.status().as_u16(),
                headers: public_headers(response.headers()),
            })?;
            Err(reject_http(
                response.status().as_u16(),
                format!(
                    "exchange WebSocket upgrade rejected with HTTP {}",
                    response.status()
                ),
            ))
        }
        Err(error) => bail!("WebSocket upgrade failed: {error}"),
    }
}

pub fn set_io_timeout(socket: &Socket, timeout: Duration) -> Result<()> {
    let tcp = match socket.get_ref() {
        MaybeTlsStream::Plain(tcp) => tcp,
        MaybeTlsStream::NativeTls(tls) => tls.get_ref(),
        _ => bail!("unsupported TLS stream"),
    };
    tcp.set_read_timeout(Some(timeout))?;
    tcp.set_write_timeout(Some(timeout))?;
    Ok(())
}

fn connect_tcp(host: &str, port: u16, timeout: Duration) -> Result<TcpStream> {
    let started = Instant::now();
    let addresses = (host, port)
        .to_socket_addrs()
        .context("resolve connection hostname")?;
    let mut last_error = None;
    for address in addresses {
        let remaining = timeout.saturating_sub(started.elapsed());
        if remaining.is_zero() {
            break;
        }
        match TcpStream::connect_timeout(&address, remaining) {
            Ok(stream) => return Ok(stream),
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error
        .map(anyhow::Error::from)
        .unwrap_or_else(|| anyhow::anyhow!("connection timed out or hostname has no addresses")))
    .context("TCP connection failed")
}

fn configured_proxy(host: &str, port: u16) -> Result<Option<Url>> {
    let no_proxy = nonempty_env("no_proxy").or_else(|| nonempty_env("NO_PROXY"));
    if no_proxy.is_some_and(|rules| bypass_proxy(host, port, &rules)) {
        return Ok(None);
    }
    let proxy = nonempty_env("https_proxy")
        .or_else(|| nonempty_env("HTTPS_PROXY"))
        .or_else(|| nonempty_env("all_proxy"))
        .or_else(|| nonempty_env("ALL_PROXY"));
    let Some(proxy) = proxy else { return Ok(None) };
    let url = Url::parse(&proxy).map_err(|_| anyhow::anyhow!("invalid proxy URL"))?;
    ensure!(
        url.scheme() == "http",
        "only HTTP CONNECT proxies are currently supported"
    );
    ensure!(url.host_str().is_some(), "proxy URL requires a hostname");
    Ok(Some(url))
}

fn nonempty_env(name: &str) -> Option<String> {
    env::var(name).ok().filter(|value| !value.is_empty())
}

pub fn bypass_proxy(host: &str, port: u16, rules: &str) -> bool {
    let host = host.to_ascii_lowercase();
    rules.split(',').any(|rule| {
        let rule = rule.trim().to_ascii_lowercase();
        if rule == "*" {
            return true;
        }
        let (domain, required_port) = rule
            .rsplit_once(':')
            .filter(|(_, port)| port.parse::<u16>().is_ok())
            .map_or((rule.as_str(), None), |(domain, port)| {
                (domain, port.parse::<u16>().ok())
            });
        if required_port.is_some_and(|required| required != port) {
            return false;
        }
        let domain = domain.trim_start_matches('.');
        !domain.is_empty() && (host == domain || host.ends_with(&format!(".{domain}")))
    })
}

pub fn establish_tunnel(
    stream: &mut (impl Read + Write),
    host: &str,
    port: u16,
    proxy: &Url,
) -> Result<()> {
    let mut request = format!("CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n");
    if !proxy.username().is_empty() || proxy.password().is_some() {
        let username = percent_decode_str(proxy.username())
            .decode_utf8()
            .context("proxy username is not UTF-8")?;
        let password = percent_decode_str(proxy.password().unwrap_or_default())
            .decode_utf8()
            .context("proxy password is not UTF-8")?;
        request.push_str(&format!(
            "Proxy-Authorization: Basic {}\r\n",
            STANDARD.encode(format!("{username}:{password}"))
        ));
    }
    request.push_str("\r\n");
    stream
        .write_all(request.as_bytes())
        .context("write proxy CONNECT request")?;
    stream.flush()?;
    // Read exactly the headers. Buffering beyond them could consume TLS bytes.
    let mut response = Vec::new();
    while !response.ends_with(b"\r\n\r\n") {
        ensure!(
            response.len() < MAX_HANDSHAKE_BYTES,
            "proxy response headers too large"
        );
        let mut byte = [0_u8];
        stream
            .read_exact(&mut byte)
            .context("read proxy CONNECT response")?;
        response.push(byte[0]);
    }
    let text = std::str::from_utf8(&response).context("proxy returned non-UTF-8 headers")?;
    let mut status = text.lines().next().unwrap_or_default().split_whitespace();
    ensure!(
        matches!(status.next(), Some("HTTP/1.1" | "HTTP/1.0")),
        "invalid proxy response protocol"
    );
    let code = status
        .next()
        .and_then(|s| s.parse::<u16>().ok())
        .context("proxy returned no HTTP status")?;
    if code != 200 {
        return Err(reject_http(
            code,
            format!(
                "HTTP proxy rejected CONNECT with status {code}; check access to the exchange API domain"
            ),
        ));
    }
    Ok(())
}

fn public_headers(headers: &HeaderMap) -> BTreeMap<String, String> {
    // Allowlist rather than a denylist: credentials and cookies never enter logs.
    const ALLOWED: &[&str] = &[
        "host",
        "connection",
        "upgrade",
        "sec-websocket-version",
        "sec-websocket-key",
        "sec-websocket-accept",
        "date",
        "server",
    ];
    headers
        .iter()
        .filter(|(name, _)| ALLOWED.contains(&name.as_str()))
        .map(|(name, value)| {
            (
                name.to_string(),
                value.to_str().unwrap_or("<non-UTF-8>").to_string(),
            )
        })
        .collect()
}
