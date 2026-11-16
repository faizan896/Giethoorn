use std::io::{Cursor, Read, Write};

use giethoorn::transport::{bypass_proxy, establish_tunnel};
use url::Url;

struct Duplex {
    input: Cursor<Vec<u8>>,
    written: Vec<u8>,
}
impl Read for Duplex {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        self.input.read(buffer)
    }
}
impl Write for Duplex {
    fn write(&mut self, buffer: &[u8]) -> std::io::Result<usize> {
        self.written.extend_from_slice(buffer);
        Ok(buffer.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

#[test]
fn connect_preserves_bytes_after_proxy_headers() {
    let mut stream = Duplex {
        input: Cursor::new(b"HTTP/1.1 200 Connection established\r\n\r\nTLS-BYTES".to_vec()),
        written: Vec::new(),
    };
    establish_tunnel(
        &mut stream,
        "api.hyperliquid.xyz",
        443,
        &Url::parse("http://proxy:8080").unwrap(),
    )
    .unwrap();
    let mut remainder = String::new();
    stream.read_to_string(&mut remainder).unwrap();
    assert_eq!(remainder, "TLS-BYTES");
    assert_eq!(
        String::from_utf8(stream.written).unwrap(),
        "CONNECT api.hyperliquid.xyz:443 HTTP/1.1\r\nHost: api.hyperliquid.xyz:443\r\n\r\n"
    );
}

#[test]
fn proxy_denial_reports_status_without_leaking_credentials() {
    let mut stream = Duplex {
        input: Cursor::new(b"HTTP/1.1 403 Forbidden\r\n\r\n".to_vec()),
        written: Vec::new(),
    };
    let error = establish_tunnel(
        &mut stream,
        "api.hyperliquid.xyz",
        443,
        &Url::parse("http://example:dummy-password@proxy:8080").unwrap(),
    )
    .unwrap_err();
    assert!(error.to_string().contains("403"));
    assert!(!error.to_string().contains("dummy-password"));
}

#[test]
fn proxy_basic_auth_decodes_url_escaped_credentials() {
    let mut stream = Duplex {
        input: Cursor::new(b"HTTP/1.0 200 OK\r\n\r\n".to_vec()),
        written: Vec::new(),
    };
    establish_tunnel(
        &mut stream,
        "api.hyperliquid.xyz",
        443,
        &Url::parse("http://user:p%40ss@proxy:8080").unwrap(),
    )
    .unwrap();
    assert!(
        String::from_utf8(stream.written)
            .unwrap()
            .contains("Proxy-Authorization: Basic dXNlcjpwQHNz\r\n")
    );
}

#[test]
fn truncated_and_oversized_proxy_responses_are_rejected() {
    for input in [b"HTTP/1.1 200 OK\r\n".to_vec(), vec![b'a'; 32769]] {
        let mut stream = Duplex {
            input: Cursor::new(input),
            written: Vec::new(),
        };
        assert!(
            establish_tunnel(
                &mut stream,
                "example.com",
                443,
                &Url::parse("http://proxy:8080").unwrap()
            )
            .is_err()
        );
    }
}

#[test]
fn no_proxy_respects_domain_boundaries_and_ports() {
    assert!(bypass_proxy(
        "API.HYPERLIQUID.XYZ",
        443,
        "localhost, .hyperliquid.xyz"
    ));
    assert!(bypass_proxy("hyperliquid.xyz", 443, "hyperliquid.xyz:443"));
    assert!(!bypass_proxy(
        "api.hyperliquid.xyz",
        80,
        "hyperliquid.xyz:443"
    ));
    assert!(!bypass_proxy("evilhyperliquid.xyz", 443, "hyperliquid.xyz"));
    assert!(!bypass_proxy(
        "hyperliquid.xyz.evil.example",
        443,
        "hyperliquid.xyz"
    ));
    assert!(bypass_proxy("127.0.0.1", 1234, "127.0.0.1"));
    assert!(bypass_proxy("anything", 443, "*"));
}
