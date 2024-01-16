from unittest.mock import patch

from twisted.trial.unittest import TestCase
from twisted.internet import defer

from scrapy import Request, Spider
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.http import Response
from scrapy.settings import Settings
from scrapy.utils.test import get_crawler
from scrapy.crawler import CrawlerRunner


TEST_SETTINGS = {
    'SCHEDULER': 'scrapy_frontera.scheduler.FronteraScheduler',
    'BACKEND': 'frontera.contrib.backends.memory.FIFO',
    'DOWNLOADER_MIDDLEWARES': {
        'scrapy_frontera.middlewares.SchedulerDownloaderMiddleware': 0,
    },
    'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7',
    'SPIDER_MIDDLEWARES': {
        'scrapy_frontera.middlewares.SchedulerSpiderMiddleware': 0,
    },
}


class _TestSpider(Spider):
    name = 'test'
    success = False
    success2 = False
    success3 = False
    error = False

    def start_requests(self):
        yield Request('http://example.com')

    def parse(self, response):
        self.success = True
        if response.body == b'cf_store':
            yield Request('http://example2.com', callback=self.parse2, errback=self.errback,
                          meta={'cf_store': True})
        else:
            yield Request('http://example2.com', callback=self.parse2, errback=self.errback)

    def parse2(self, response):
        self.success2 = True

    def errback(self, failure):
        self.error = True
        response = failure.value.response
        if response.body == b'cf_store':
            yield Request('http://example3.com', callback=self.parse3, meta={'cf_store': True})
        else:
            yield Request('http://example3.com', callback=self.parse3)

    def parse3(self, response):
        self.success3 = True


class _TestSpider2(Spider):
    name = 'test'
    success = False
    success2 = False

    def start_requests(self):
        yield Request('http://example.com')

    def parse(self, response):
        self.success = True
        yield Request('http://example2.com', callback=self.parse2)

    def parse2(self, response):
        self.success2 = True


class _TestSpider3(Spider):
    name = 'test'
    success = 0

    def start_requests(self):
        yield Request('http://example.com')

    def parse(self, response):
        self.success += 1
        yield Request('http://example2.com')


class TestDownloadHandler:

    results = []

    def set_results(self, results):
        for r in results:
            self.results.append(r)

    def download_request(self, request, spider):
        return self.results.pop(0)

    def close(self):
        pass


class FronteraSchedulerTest(TestCase):

    def setUp(self):
        self.runner = CrawlerRunner()

    def tearDown(self):
        self.runner.stop()
        while TestDownloadHandler.results:
            TestDownloadHandler.results.pop()

    @staticmethod
    def setup_mocked_handler(mocked_handler, results=None):
        handler = TestDownloadHandler()
        if results:
            handler.set_results(results)
        if hasattr(HTTP11DownloadHandler, "from_crawler"):
            mocked_handler.from_crawler.return_value = handler
        else:
            mocked_handler.return_value = handler


    @defer.inlineCallbacks
    def test_start_requests(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(
                mocked_handler,
                [
                    Response(url='http://example.com'),
                    Response(url='http://example2.com'),
                ],
            )

            with patch('frontera.contrib.backends.memory.MemoryBaseBackend.links_extracted') as mocked_links_extracted:
                mocked_links_extracted.return_value = None
                settings = Settings()
                settings.setdict(TEST_SETTINGS, priority='cmdline')
                crawler = get_crawler(_TestSpider, settings)

                yield self.runner.crawl(crawler)
                self.assertTrue(crawler.spider.success)
                self.assertTrue(crawler.spider.success2)
                mocked_links_extracted.assert_not_called()

    @defer.inlineCallbacks
    def test_cf_store(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(
                mocked_handler,
                [
                    Response(url='http://example.com', body=b'cf_store'),
                ],
            )

            with patch('frontera.contrib.backends.memory.MemoryDequeQueue.schedule') as mocked_schedule:
                mocked_schedule.return_value = None
                settings = Settings()
                settings.setdict(TEST_SETTINGS, priority='cmdline')
                crawler = get_crawler(_TestSpider, settings)

                yield self.runner.crawl(crawler)
                self.assertTrue(crawler.spider.success)
                self.assertEqual(mocked_schedule.call_count, 1)

    @defer.inlineCallbacks
    def test_callback_requests_to_frontier(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(
                mocked_handler,
                [
                    Response(url='http://example.com'),
                ],
            )

            with patch('frontera.contrib.backends.memory.MemoryDequeQueue.schedule') as mocked_schedule:
                mocked_schedule.return_value = None
                settings = Settings()
                settings.setdict(TEST_SETTINGS, priority='cmdline')
                settings.setdict({
                    'FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER': ['parse2'],
                })
                crawler = get_crawler(_TestSpider2, settings)

                yield self.runner.crawl(crawler)
                self.assertTrue(crawler.spider.success)
                self.assertFalse(crawler.spider.success2)
                self.assertEqual(mocked_schedule.call_count, 1)

    @defer.inlineCallbacks
    def test_callback_requests_to_frontier_with_implicit_callback(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(
                mocked_handler,
                [
                    Response(url='http://example.com'),
                    Response(url='http://example2.com'),
                ],
            )

            with patch('frontera.contrib.backends.memory.MemoryDequeQueue.schedule') as mocked_schedule:
                mocked_schedule.return_value = None
                settings = Settings()
                settings.setdict(TEST_SETTINGS, priority='cmdline')
                settings.setdict({
                    'FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER': ['parse'],
                })
                crawler = get_crawler(_TestSpider3, settings)

                yield self.runner.crawl(crawler)
                self.assertEqual(crawler.spider.success, 1)
                self.assertEqual(mocked_schedule.call_count, 1)

    @defer.inlineCallbacks
    def test_callback_requests_slot_map(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            resp1 = Response(url='http://example.com')
            resp2 = Response(url='http://example2.com')
            self.setup_mocked_handler(mocked_handler, [resp1, resp2])

            with patch('frontera.contrib.backends.memory.MemoryDequeQueue.schedule') as mocked_schedule:
                mocked_schedule.return_value = None
                settings = Settings()
                settings.setdict(TEST_SETTINGS, priority='cmdline')
                settings.setdict({
                    'FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER': ['parse'],
                    'FRONTERA_SCHEDULER_CALLBACK_SLOT_PREFIX_MAP': {'parse': 'myslot'},
                })
                crawler = get_crawler(_TestSpider3, settings)

                yield self.runner.crawl(crawler)
                self.assertEqual(crawler.spider.success, 1)
                self.assertEqual(mocked_schedule.call_count, 1)
                frontera_request = mocked_schedule.call_args_list[0][0][0][0][2]
                self.assertEqual(frontera_request.url, resp2.url)
                self.assertEqual(frontera_request.meta[b'frontier_slot_prefix'], 'myslot')

    @defer.inlineCallbacks
    def test_callback_requests_slot_map_with_num_slots(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            resp1 = Response(url='http://example.com')
            resp2 = Response(url='http://example2.com')
            self.setup_mocked_handler(mocked_handler, [resp1, resp2])

            with patch('frontera.contrib.backends.memory.MemoryDequeQueue.schedule') as mocked_schedule:
                mocked_schedule.return_value = None
                settings = Settings()
                settings.setdict(TEST_SETTINGS, priority='cmdline')
                settings.setdict({
                    'FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER': ['parse'],
                    'FRONTERA_SCHEDULER_CALLBACK_SLOT_PREFIX_MAP': {'parse': 'myslot/5'},
                })
                crawler = get_crawler(_TestSpider3, settings)

                yield self.runner.crawl(crawler)
                self.assertEqual(crawler.spider.success, 1)
                self.assertEqual(mocked_schedule.call_count, 1)
                frontera_request = mocked_schedule.call_args_list[0][0][0][0][2]
                self.assertEqual(frontera_request.url, resp2.url)
                self.assertEqual(frontera_request.meta[b'frontier_slot_prefix'], 'myslot')
                self.assertEqual(frontera_request.meta[b'frontier_number_of_slots'], 5)

    @defer.inlineCallbacks
    def test_start_requests_to_frontier(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(
                mocked_handler,
                [
                    Response(url='http://example.com'),
                    Response(url='http://example2.com'),
                ],
            )

            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority='cmdline')
            settings.setdict({
                'FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER': True,
            })
            crawler = get_crawler(_TestSpider, settings)

            yield self.runner.crawl(crawler)
            self.assertTrue(crawler.spider.success)
            self.assertTrue(crawler.spider.success2)

    @defer.inlineCallbacks
    def test_start_requests_to_frontier_ii(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(mocked_handler)

            with patch('frontera.contrib.backends.memory.MemoryBaseBackend.add_seeds') as mocked_add_seeds:
                mocked_add_seeds.return_value = None
                settings = Settings()
                settings.setdict(TEST_SETTINGS, priority='cmdline')
                settings.setdict({
                    'FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER': True,
                })

                crawler = get_crawler(_TestSpider, settings)

                yield self.runner.crawl(crawler)
                self.assertEqual(mocked_add_seeds.call_count, 1)

    @defer.inlineCallbacks
    def test_start_handle_errback(self):
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(
                mocked_handler,
                [
                    Response(url='http://example.com'),
                    Response(url='http://example2.com', status=501),
                    Response(url='http://example3.com'),
                ],
            )

            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority='cmdline')
            crawler = get_crawler(_TestSpider, settings)

            yield self.runner.crawl(crawler)
            self.assertTrue(crawler.spider.success)
            self.assertFalse(crawler.spider.success2)
            self.assertTrue(crawler.spider.error)
            self.assertTrue(crawler.spider.success3)

    @defer.inlineCallbacks
    def test_start_handle_errback_with_cf_store(self):
        """
        Test that we get the expected result with errback cf_store
        """
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(
                mocked_handler,
                [
                    Response(url='http://example.com'),
                    Response(url='http://example2.com', status=501, body=b'cf_store'),
                    Response(url='http://example3.com'),
                ],
            )

            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority='cmdline')
            crawler = get_crawler(_TestSpider, settings)

            yield self.runner.crawl(crawler)
            self.assertTrue(crawler.spider.success)
            self.assertFalse(crawler.spider.success2)
            self.assertTrue(crawler.spider.error)
            self.assertTrue(crawler.spider.success3)

    @defer.inlineCallbacks
    def test_start_handle_errback_with_cf_store_ii(self):
        """
        Test that we scheduled cf_store request on backend queue
        """
        with patch('scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler') as mocked_handler:
            self.setup_mocked_handler(
                mocked_handler,
                [
                    Response(url='http://example.com'),
                    Response(url='http://example2.com', status=501, body=b'cf_store'),
                    Response(url='http://example3.com'),
                ],
            )

            with patch('frontera.contrib.backends.memory.MemoryDequeQueue.schedule') as mocked_schedule:
                mocked_schedule.return_value = None
                settings = Settings()
                settings.setdict(TEST_SETTINGS, priority='cmdline')
                crawler = get_crawler(_TestSpider, settings)

                yield self.runner.crawl(crawler)
                self.assertTrue(crawler.spider.success)
                self.assertFalse(crawler.spider.success2)
                self.assertTrue(crawler.spider.error)
                self.assertEqual(mocked_schedule.call_count, 1)
