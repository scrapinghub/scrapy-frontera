from unittest.mock import patch

from twisted.trial.unittest import TestCase
from twisted.internet import defer

from scrapy import Request, Spider
from scrapy.http import Response
from scrapy.settings import Settings
from scrapy.utils.test import get_crawler
from scrapy.crawler import CrawlerRunner

from frontera.contrib.backends import CommonBackend


TEST_SETTINGS = {
    'SCHEDULER': 'scrapy_frontera.scheduler.FronteraScheduler',
    'BACKEND': 'frontera.contrib.backends.memory.FIFO',
    'DOWNLOADER_MIDDLEWARES': {
        'scrapy_frontera.middlewares.SchedulerDownloaderMiddleware': 999,
    },
    'SPIDER_MIDDLEWARES': {
        'scrapy_frontera.middlewares.SchedulerSpiderMiddleware': 999,
    },
}


class TestSpider(Spider):
    name = 'test'
    success = False

    def start_requests(self):
        yield Request('http://example.com')

    def parse(self, response):
        self.success = True


class TestDownloadHandler:
    def __init__(self):
        self.results = []

    def set_results(results):
        self.results = results

    def download_request(self, request, spider):
        return self.results.pop(0)

    def close(self):
        pass


class FronteraSchedulerTest(TestCase):
    
    @patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler')
    def setUp(self, mocked_handler):
        self.runner = CrawlerRunner()
        self.mocked_handler = mocked_handler
        self.mocked_handler.return_value = TestDownloadHandler()

    def tearDown(self):
        self.runner.stop()

    @defer.inlineCallbacks
    def test_start_requests(self):
        settings = Settings()
        settings.setdict(TEST_SETTINGS, priority='cmdline')
        crawler = get_crawler(TestSpider, settings)

        self.mocked_handler.set_results([Response(url='http://example.com')])
        yield self.runner.crawl(crawler)
        self.assertTrue(crawler.spider.success)

    @defer.inlineCallbacks
    def test_start_requests_to_frontier(self):
        settings = Settings()
        settings.setdict(TEST_SETTINGS, priority='cmdline')
        settings.setdict({
            'FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER': True,
        })
        crawler = get_crawler(TestSpider, settings)

        self.mocked_handler.set_results([Response(url='http://example.com')])
        yield self.runner.crawl(crawler)
        self.assertTrue(crawler.spider.success)

    @defer.inlineCallbacks
    def test_start_requests_to_frontier_ii(self):
        with patch('frontera.contrib.backends.memory.MemoryBaseBackend.add_seeds') as mocked_add_seeds:
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority='cmdline')
            settings.setdict({
                'FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER': True,
            })

            crawler = get_crawler(TestSpider, settings)

            self.mocked_handler.set_results([Response(url='http://example.com')])
            mocked_add_seeds.return_value = None
            yield self.runner.crawl(crawler)
            self.assertFalse(crawler.spider.success)
            self.assertEqual(mocked_add_seeds.call_count, 1)
