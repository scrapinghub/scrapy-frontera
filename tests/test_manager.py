from scrapy import Request, Spider, signals
from scrapy.utils.test import get_crawler
from twisted.internet.defer import inlineCallbacks

from scrapy_frontera.manager import ScrapyFrontierManager


@inlineCallbacks
def test_add_seeds():
    class TestSpider(Spider):
        name = "test_spider"

    seeds = [Request("https://toscrape.com", dont_filter=True)]
    manager = ScrapyFrontierManager()

    def spider_open():
        manager.set_spider(crawler.spider)
        manager.add_seeds(seeds)

    crawler = get_crawler(TestSpider)
    crawler.signals.connect(spider_open, signal=signals.spider_opened)
    yield crawler.crawl()

    processed_requests = manager.get_next_requests()

    def serialize_request(request):
        return request.to_dict(spider=crawler.spider)

    expected = [serialize_request(request) for request in seeds]
    actual = [serialize_request(request) for request in processed_requests]
    assert expected == actual
