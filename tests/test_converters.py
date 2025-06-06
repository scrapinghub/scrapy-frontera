import pytest
from frontera.core.models import Request as FrontierRequest
from scrapy import Request as ScrapyRequest
from scrapy import Spider, signals
from scrapy.utils.test import get_crawler
from twisted.internet.defer import inlineCallbacks

from scrapy_frontera.converters import RequestConverter


@inlineCallbacks
@pytest.mark.parametrize(
    ("input_request", "expected_request"),
    [
        (
            ScrapyRequest("https://toscrape.com"),
            FrontierRequest(
                "https://toscrape.com",
                meta={
                    b"frontier_fingerprint": "9769dedaf9ca0515c1e761ac814e15171e1e4032",
                    b"origin_is_frontier": True,
                    b"scrapy_body": b"",
                    b"scrapy_callback": None,
                    b"scrapy_cb_kwargs": {},
                    b"scrapy_errback": None,
                    b"scrapy_meta": {},
                    b"spider_state": [],
                },
            ),
        )
    ],
)
def test_to_frontier(input_request, expected_request):
    class TestSpider(Spider):
        name = "test_spider"

    actual_requests = []

    def spider_open():
        converter = RequestConverter(crawler.spider)
        actual_requests.append(converter.to_frontier(input_request))

    crawler = get_crawler(TestSpider)
    crawler.signals.connect(spider_open, signal=signals.spider_opened)
    yield crawler.crawl()

    assert len(actual_requests) == 1
    actual_request = actual_requests[0]

    # hcf-backend requires fingerprints to be strings.
    assert isinstance(actual_request.meta[b"frontier_fingerprint"], str)

    def serialize_frontier_request(request):
        return request.__dict__

    assert serialize_frontier_request(expected_request) == serialize_frontier_request(
        actual_request
    )
