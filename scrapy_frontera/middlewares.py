class BaseSchedulerMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    @property
    def scheduler(self):
        try:
            # To be exposed as engine.scheduler as part of
            # https://github.com/scrapy/scrapy/pull/6715
            return self.crawler.engine._slot.scheduler
        except AttributeError:  # Scrapy < 2.13.0
            return self.crawler.engine.slot.scheduler


class SchedulerSpiderMiddleware(BaseSchedulerMiddleware):
    def process_spider_output(self, response, result, spider):
        return self.scheduler.process_spider_output(response, result, spider)

    async def process_spider_output_async(self, response, result, spider):
        async for item_or_request in self.scheduler.process_spider_output_async(
            response, result, spider
        ):
            yield item_or_request

    def _skip_start_requests(self):
        return self.crawler.settings.getbool(
            "FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER"
        ) or self.crawler.settings.getbool("FRONTERA_SCHEDULER_SKIP_START_REQUESTS")

    async def process_start(self, start):
        if self._skip_start_requests():
            return
        async for item_or_request in start:
            yield item_or_request

    def process_start_requests(self, start_requests, spider):
        if self._skip_start_requests():
            return []
        return start_requests


class SchedulerDownloaderMiddleware(BaseSchedulerMiddleware):
    def process_exception(self, request, exception, spider):
        return self.scheduler.process_exception(request, exception, spider)
