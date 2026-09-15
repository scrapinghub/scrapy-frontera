import logging
from contextlib import ExitStack, contextmanager
from unittest.mock import PropertyMock, patch

from scrapy import Request, Spider
from scrapy.http import Response
from scrapy.settings import Settings, default_settings
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks

# Patch the class DOWNLOAD_HANDLERS_BASE actually registers for "http": the
# http11 and http module paths have swapped which one is the real target and
# which is a deprecated re-export across Scrapy versions, so hardcoding
# either one can silently no-op and leak real network requests.
DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH = default_settings.DOWNLOAD_HANDLERS_BASE["http"]
DefaultDownloadHandlerClass = load_object(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH)


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


class _ChainSpider(BaseSpider):
    name = "test"
    timeline = None

    def start_requests(self):
        yield Request("http://start.example")

    def parse(self, response):
        self.timeline.append(("parse", response.url))
        if response.url == "http://start.example":
            yield Request("http://child.example", callback=self.parse_child)

    def parse_child(self, response):
        self.timeline.append(("parse", response.url))


class _EmptyStartSpider(BaseSpider):
    name = "test"

    def start_requests(self):
        return iter([])

    def parse(self, response):
        pass


class MockDownloadHandler:
    def __init__(self):
        self.results = []

    def set_results(self, results):
        for r in results:
            self.results.append(r)

    def download_request(self, request, spider=None):
        # Sync, returning an already-fired Deferred: Scrapy's calling
        # convention for this method (sync vs. awaited coroutine, with or
        # without a positional spider argument) has changed across versions;
        # this satisfies all of them. Falls back to an empty 200 response for
        # the given URL when no scripted result is queued, so tests that
        # don't care about response content don't need to pre-script one.
        response = self.results.pop(0) if self.results else Response(url=request.url)
        return defer.succeed(response)

    def close(self):
        return defer.succeed(None)


def setup_mocked_handler(mocked_handler, results=None):
    handler = MockDownloadHandler()
    if results:
        handler.set_results(results)
    if hasattr(DefaultDownloadHandlerClass, "from_crawler"):
        mocked_handler.from_crawler.return_value = handler
    else:
        mocked_handler.return_value = handler


def first_index(timeline, event):
    return next(i for i, ev in enumerate(timeline) if ev == event)


@contextmanager
def patch_backend(timeline, requests):
    """
    Make the frontier hand out `requests` once, recording every backend read
    in `timeline`. The memory backend reports itself finished while its
    (unseeded) queue is empty, which would short-circuit
    _get_requests_from_backend() before get_next_requests() is ever reached.
    """
    pending = [list(requests)]

    def get_next_requests(max_next_requests=0, **kwargs):
        timeline.append(("backend_fetch",))
        return pending.pop() if pending else []

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "scrapy_frontera.manager.ScrapyFrontierManager.get_next_requests",
                side_effect=get_next_requests,
            )
        )
        stack.enter_context(
            patch(
                "frontera.core.manager.FrontierManager.finished",
                new_callable=PropertyMock,
                return_value=False,
            )
        )
        yield


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


@inlineCallbacks
def test_delay_frontier_until_idle_disabled_by_default():
    """
    With FRONTERA_SCHEDULER_DELAY_FRONTIER_UNTIL_IDLE unset (default False),
    behavior is unchanged: the frontier can be read before the start
    request's chain has finished.
    """
    timeline = []
    _ChainSpider.timeline = timeline
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(mocked_handler)
        with patch_backend(timeline, [Request("http://frontier.example")]):
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            crawler = get_crawler(_ChainSpider, settings)
            yield crawler.crawl()

    assert first_index(timeline, ("backend_fetch",)) < first_index(
        timeline, ("parse", "http://child.example")
    )


@inlineCallbacks
def test_delay_frontier_until_idle():
    """
    With the setting on, the frontier isn't read until the spider goes idle
    - i.e. not just after the start request, but after everything reachable
    from it through the scrapy scheduler (here, its child request) too.
    """
    timeline = []
    _ChainSpider.timeline = timeline
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(mocked_handler)
        with patch_backend(timeline, [Request("http://frontier.example")]):
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            settings.setdict({"FRONTERA_SCHEDULER_DELAY_FRONTIER_UNTIL_IDLE": True})
            crawler = get_crawler(_ChainSpider, settings)
            yield crawler.crawl()

    fetch_i = first_index(timeline, ("backend_fetch",))
    assert fetch_i > first_index(timeline, ("parse", "http://start.example"))
    assert fetch_i > first_index(timeline, ("parse", "http://child.example"))
    assert ("parse", "http://frontier.example") in timeline


@inlineCallbacks
def test_delay_frontier_until_idle_ignored_with_start_requests_to_frontier(caplog):
    """
    The setting is meaningless when start requests are diverted into the
    frontier as seeds - it must be ignored (with a warning), not deadlock
    the crawl.
    """
    caplog.set_level(logging.WARNING)
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
                "FRONTERA_SCHEDULER_DELAY_FRONTIER_UNTIL_IDLE": True,
            }
        )
        crawler = get_crawler(_TestSpider, settings)
        yield crawler.crawl()
        assert crawler.spider.success
        assert crawler.spider.success2

    assert any(
        "FRONTERA_SCHEDULER_DELAY_FRONTIER_UNTIL_IDLE" in record.message
        for record in caplog.records
    )


@inlineCallbacks
def test_delay_frontier_until_idle_ignored_with_skip_start_requests(caplog):
    """
    Same as above, for FRONTERA_SCHEDULER_SKIP_START_REQUESTS: the gate must
    not stay shut waiting for start requests that will never be scheduled.
    """
    caplog.set_level(logging.WARNING)
    timeline = []
    _ChainSpider.timeline = timeline
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(mocked_handler)
        with patch_backend(timeline, [Request("http://frontier.example")]):
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            settings.setdict(
                {
                    "FRONTERA_SCHEDULER_SKIP_START_REQUESTS": True,
                    "FRONTERA_SCHEDULER_DELAY_FRONTIER_UNTIL_IDLE": True,
                }
            )
            crawler = get_crawler(_ChainSpider, settings)
            yield crawler.crawl()

    assert ("parse", "http://frontier.example") in timeline
    assert any(
        "FRONTERA_SCHEDULER_DELAY_FRONTIER_UNTIL_IDLE" in record.message
        for record in caplog.records
    )


@inlineCallbacks
def test_delay_frontier_until_idle_with_empty_start_requests():
    """
    A spider with no start requests must not hang waiting for spider_idle to
    open the gate - it fires almost immediately, and the crawl still
    completes normally.
    """
    timeline = []
    with patch(DEFAULT_DOWNLOAD_HANDLER_IMPORT_PATH) as mocked_handler:
        setup_mocked_handler(mocked_handler)
        with patch_backend(timeline, [Request("http://frontier.example")]):
            settings = Settings()
            settings.setdict(TEST_SETTINGS, priority="cmdline")
            settings.setdict({"FRONTERA_SCHEDULER_DELAY_FRONTIER_UNTIL_IDLE": True})
            crawler = get_crawler(_EmptyStartSpider, settings)
            yield crawler.crawl()

    assert ("backend_fetch",) in timeline
    assert crawler.stats.get_value("finish_reason") == "finished"
