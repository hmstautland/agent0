import tools.web as webmod


def test_extract_text_from_html():
    html = "<html><head><style>p{}</style><script>console.log('x')</script></head><body><h1>Title</h1><p>Content</p></body></html>"
    text = webmod._extract_text_from_html(html)

    assert "Title" in text
    assert "Content" in text
    assert "script" not in text
    assert "style" not in text


def test_read_web_content_with_mocked_requests(monkeypatch):
    class MockResponse:
        status_code = 200
        text = "<html><body><h1>Hello world</h1></body></html>"

    monkeypatch.setattr(webmod.requests, "get", lambda url, timeout: MockResponse())

    result = webmod.read_web_content(["https://example.com"])

    assert "https://example.com" in result
    assert "Hello world" in result["https://example.com"]
