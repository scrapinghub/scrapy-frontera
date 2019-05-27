

class BaseSchedulerMiddleware(object):

    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    @property
    def scheduler(self):
        return self.crawler.engine.slot.scheduler


class SchedulerSpiderMiddleware(BaseSchedulerMiddleware):
    def process_spider_output(self, response, result, spider):
        return self.scheduler.process_spider_output(response, result, spider)

    def process_start_requests(self, start_requests, spider):
        if self.crawler.settings.getbool('FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER'):
            return []
        return start_requests


class SchedulerDownloaderMiddleware(BaseSchedulerMiddleware):
    def process_exception(self, request, exception, spider):
        return self.scheduler.process_exception(request, exception, spider)
