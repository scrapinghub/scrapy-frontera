from scrapy_frontera.core.manager import FrontierManager

from .converters import RequestConverter, ResponseConverter


class ScrapyFrontierManager:
    spider = None

    def set_spider(self, spider):
        assert self.spider is None, (
            "Spider is already set. Only one spider is supported per process."
        )
        self.spider = spider
        self.request_converter = RequestConverter(self.spider)
        self.response_converter = ResponseConverter(self.spider, self.request_converter)

    def __init__(self, settings=None):
        self.manager = FrontierManager.from_settings(settings)

    def start(self):
        self.manager.start()

    def stop(self):
        self.manager.stop()

    def add_seeds(self, seeds):
        frontier_seeds = [self.request_converter.to_frontier(seed) for seed in seeds]
        self.manager.add_seeds(seeds=frontier_seeds)

    def get_next_requests(self, max_next_requests=0, **kwargs):
        frontier_requests = self.manager.get_next_requests(
            max_next_requests=max_next_requests, **kwargs
        )
        return [
            self.request_converter.from_frontier(frontier_request)
            for frontier_request in frontier_requests
        ]

    def page_crawled(self, response):
        frontier_response = self.response_converter.to_frontier(response)
        self.manager.page_crawled(frontier_response)

    def links_extracted(self, request, links):
        frontera_request = self.request_converter.to_frontier(request)
        frontera_links = [self.request_converter.to_frontier(link) for link in links]
        self.manager.links_extracted(frontera_request, frontera_links)

    def request_error(self, request, error):
        self.manager.request_error(
            request=self.request_converter.to_frontier(request), error=error
        )
