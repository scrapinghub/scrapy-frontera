from unittest.mock import patch

from scrapy import Request, Spider
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.http import Response
from scrapy.settings import Settings
from scrapy.utils.test import get_crawler
from twisted.internet.defer import inlineCallbacks

try:
    from scrapy.core.downloader.handlers.http import HTTPDownloadHandler  # noqa: F401
except ImportError:  # Scrapy < 2.13
    DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH = (
        "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler"
    )
else:
    DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH = (
        "scrapy.core.downloader.handlers.http.HTTPDownloadHandler"
    )


TEST_SETTINGS = {
    "SCHEDULER": "scrapy_frontera.scheduler.FronteraScheduler",
    "BACKEND": "frontera.contrib.backends.memory.FIFO",
    "DOWNLOADER_MIDDLEWARES": {
        "scrapy_frontera.middlewares.SchedulerDownloaderMiddleware": 0,
    },
    "SPIDER_MIDDLEWARES": {
        "scrapy_frontera.middlewares.SchedulerSpiderMiddleware": 0,
    },
}


class BaseSpider(Spider):
    async def start(self):
        for item_or_request in self.start_requests():
            yield item_or_request

    def start_requests(self):
        yield Request("http://example.com")


class _TestSpider(BaseSpider):
    name = "test"
    success = False
    success2 = False
    success3 = False
    error = False

    def parse(self, response):
        self.success = True
        if response.body == b"cf_store":
            yield Request(
                "http://example2.com",
                callback=self.parse2,
                errback=self.errback,
                meta={"cf_store": True},
            )
        else:
            yield Request(
                "http://example2.com", callback=self.parse2, errback=self.errback
            )

    def parse2(self, response):
        self.success2 = True

    def errback(self, failure):
        self.error = True
        response = failure.value.response
        if response.body == b"cf_store":
            yield Request(
                "http://example3.com", callback=self.parse3, meta={"cf_store": True}
            )
        else:
            yield Request("http://example3.com", callback=self.parse3)

    def parse3(self, response):
        self.success3 = True


class _TestSpider2(BaseSpider):
    name = "test"
    success = False
    success2 = False

    def parse(self, response):
        self.success = True
        yield Request("http://example2.com", callback=self.parse2)

    def parse2(self, response):
        self.success2 = True


class _TestSpider3(BaseSpider):
    name = "test"
    success = 0

    def parse(self, response):
        self.success += 1
        yield Request("http://example2.com")


class MockDownloadHandler:
    def __init__(self):
        self.results = []

    def set_results(self, results):
        for r in results:
            self.results.append(r)

    def download_request(self, request, spider):
        return self.results.pop(0)

    def close(self):
        pass


def setup_mocked_handler(mocked_handler, results=None):
    handler = MockDownloadHandler()
    if results:
        handler.set_results(results)
    if hasattr(HTTP11DownloadHandler, "from_crawler"):
        mocked_handler.from_crawler.return_value = handler
    else:
        mocked_handler.return_value = handler


@inlineCallbacks
def test_start_requests():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(
            mocked_handler,
            [
                Response(url="http://example.com"),
                Response(url="http://example2.com"),
            ],
        )

        with patch(
            "frontera.contrib.backends.memory.MemoryBaseBackend.links_extracted"
        ) as mocked_links_extracted:
            mocked_links_extracted.return_value = None
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            crawler = get_crawler(_TestSpider, settings)
            yield crawler.crawl()
            assert crawler.spider.success
            assert crawler.spider.success2
            mocked_links_extracted.assert_not_called()


@inlineCallbacks
def test_cf_store():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(
            mocked_handler,
            [
                Response(url="http://example.com", body=b"cf_store"),
            ],
        )

        with patch(
            "frontera.contrib.backends.memory.MemoryDequeQueue.schedule"
        ) as mocked_schedule:
            mocked_schedule.return_value = None
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            crawler = get_crawler(_TestSpider, settings)
            yield crawler.crawl()
            assert crawler.spider.success
            assert mocked_schedule.call_count == 1


@inlineCallbacks
def test_callback_requests_to_frontier():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(
            mocked_handler,
            [
                Response(url="http://example.com"),
            ],
        )

        with patch(
            "frontera.contrib.backends.memory.MemoryDequeQueue.schedule"
        ) as mocked_schedule:
            mocked_schedule.return_value = None
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            settings.setdict(
                {
                    "FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER": ["parse2"],
                }
            )
            crawler = get_crawler(_TestSpider2, settings)
            yield crawler.crawl()
            assert crawler.spider.success
            assert not crawler.spider.success2
            assert mocked_schedule.call_count == 1


@inlineCallbacks
def test_callback_requests_to_frontier_with_implicit_callback():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(
            mocked_handler,
            [
                Response(url="http://example.com"),
                Response(url="http://example2.com"),
            ],
        )

        with patch(
            "frontera.contrib.backends.memory.MemoryDequeQueue.schedule"
        ) as mocked_schedule:
            mocked_schedule.return_value = None
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            settings.setdict(
                {
                    "FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER": ["parse"],
                }
            )
            crawler = get_crawler(_TestSpider3, settings)
            yield crawler.crawl()
            assert crawler.spider.success == 1
            assert mocked_schedule.call_count == 1


@inlineCallbacks
def test_callback_requests_slot_map():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        resp1 = Response(url="http://example.com")
        resp2 = Response(url="http://example2.com")
        setup_mocked_handler(mocked_handler, [resp1, resp2])

        with patch(
            "frontera.contrib.backends.memory.MemoryDequeQueue.schedule"
        ) as mocked_schedule:
            mocked_schedule.return_value = None
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            settings.setdict(
                {
                    "FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER": ["parse"],
                    "FRONTERA_SCHEDULER_CALLBACK_SLOT_PREFIX_MAP": {"parse": "myslot"},
                }
            )
            crawler = get_crawler(_TestSpider3, settings)
            yield crawler.crawl()
            assert crawler.spider.success == 1
            assert mocked_schedule.call_count == 1
            frontera_request = mocked_schedule.call_args_list[0][0][0][0][2]
            assert frontera_request.url == resp2.url
            assert frontera_request.meta[b"frontier_slot_prefix"] == "myslot"


@inlineCallbacks
def test_callback_requests_slot_map_with_num_slots():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        resp1 = Response(url="http://example.com")
        resp2 = Response(url="http://example2.com")
        setup_mocked_handler(mocked_handler, [resp1, resp2])

        with patch(
            "frontera.contrib.backends.memory.MemoryDequeQueue.schedule"
        ) as mocked_schedule:
            mocked_schedule.return_value = None
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            settings.setdict(
                {
                    "FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER": ["parse"],
                    "FRONTERA_SCHEDULER_CALLBACK_SLOT_PREFIX_MAP": {
                        "parse": "myslot/5"
                    },
                }
            )
            crawler = get_crawler(_TestSpider3, settings)
            yield crawler.crawl()
            assert crawler.spider.success == 1
            assert mocked_schedule.call_count == 1
            frontera_request = mocked_schedule.call_args_list[0][0][0][0][2]
            assert frontera_request.url == resp2.url
            assert frontera_request.meta[b"frontier_slot_prefix"] == "myslot"
            assert frontera_request.meta[b"frontier_number_of_slots"] == 5


@inlineCallbacks
def test_start_requests_to_frontier():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(
            mocked_handler,
            [
                Response(url="http://example.com"),
                Response(url="http://example2.com"),
            ],
        )

        settings = Settings()
        settings.setdict(TEST_SETTINGS, priority="cmdline")
        settings.setdict(
            {
                "FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER": True,
            }
        )
        crawler = get_crawler(_TestSpider, settings)
        yield crawler.crawl()
        assert crawler.spider.success
        assert crawler.spider.success2


@inlineCallbacks
def test_start_requests_to_frontier_ii():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(mocked_handler)

        with patch(
            "frontera.contrib.backends.memory.MemoryBaseBackend.add_seeds"
        ) as mocked_add_seeds:
            mocked_add_seeds.return_value = None
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            settings.setdict(
                {
                    "FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER": True,
                }
            )

            crawler = get_crawler(_TestSpider, settings)
            yield crawler.crawl()
            assert mocked_add_seeds.call_count == 1


@inlineCallbacks
def test_start_handle_errback():
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(
            mocked_handler,
            [
                Response(url="http://example.com"),
                Response(url="http://example2.com", status=501),
                Response(url="http://example3.com"),
            ],
        )

        settings = Settings()
        settings.setdict(TEST_SETTINGS, priority="cmdline")
        crawler = get_crawler(_TestSpider, settings)
        yield crawler.crawl()
        assert crawler.spider.success
        assert not crawler.spider.success2
        # assert crawler.spider.error
        # assert crawler.spider.success3


@inlineCallbacks
def test_start_handle_errback_with_cf_store():
    """
    Test that we get the expected result with errback cf_store
    """
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(
            mocked_handler,
            [
                Response(url="http://example.com"),
                Response(url="http://example2.com", status=501, body=b"cf_store"),
                Response(url="http://example3.com"),
            ],
        )

        settings = Settings()
        settings.setdict(TEST_SETTINGS, priority="cmdline")
        crawler = get_crawler(_TestSpider, settings)
        yield crawler.crawl()
        assert crawler.spider.success
        assert not crawler.spider.success2
        assert crawler.spider.error
        assert crawler.spider.success3


@inlineCallbacks
def test_start_handle_errback_with_cf_store_ii():
    """
    Test that we scheduled cf_store request on backend queue
    """
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(
            mocked_handler,
            [
                Response(url="http://example.com"),
                Response(url="http://example2.com", status=501, body=b"cf_store"),
                Response(url="http://example3.com"),
            ],
        )

        with patch(
            "frontera.contrib.backends.memory.MemoryDequeQueue.schedule"
        ) as mocked_schedule:
            mocked_schedule.return_value = None
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            crawler = get_crawler(_TestSpider, settings)
            yield crawler.crawl()
            assert crawler.spider.success
            assert not crawler.spider.success2
            assert crawler.spider.error
            assert mocked_schedule.call_count == 1
