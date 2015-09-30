import logging

from scrapy.core.scheduler import Scheduler
from scrapy.http import Request

from frontera.contrib.scrapy.settings_adapter import ScrapySettingsAdapter
from .manager import ScrapyFrontierManager


LOG = logging.getLogger(__name__)


class FronteraScheduler(Scheduler):

    @classmethod
    def from_crawler(cls, crawler):
        obj = super(FronteraScheduler, cls).from_crawler(crawler)
        obj.crawler = crawler
        obj.frontier = None
        return obj

    def next_request(self):
        if not self.has_pending_requests():
            self._get_requests_from_backend()
        return super(FronteraScheduler, self).next_request()

    def process_spider_output(self, response, result, spider):
        links = []
        for element in result:
            if isinstance(element, Request) and element.meta.get('cf_store', False):
                links.append(element)
            else:
                yield element
        if links:
            self.frontier.page_crawled(response=response,
                                   links=links)
            self.stats.inc_value('frontera/links_extracted_count', len(links))

    def process_exception(self, request, exception, spider):
        error_code = self._get_exception_code(exception)
        if request.meta.get('cf_store', False):
            self.frontier.request_error(request=request, error=error_code)

    def open(self, spider):
        super(FronteraScheduler, self).open(spider)
        settings = ScrapySettingsAdapter(spider.crawler.settings)
        settings.set_from_dict(getattr(spider, 'frontera_settings', {}))
        settings.set('STATS_MANAGER', self.stats)
        self.frontier = ScrapyFrontierManager(settings)

        self.frontier.set_spider(spider)
        LOG.info('Starting frontier')
        if not self.frontier.manager.auto_start:
            self.frontier.start()

    def close(self, reason):
        super(FronteraScheduler, self).close(reason)
        LOG.info('Finishing frontier (%s)' % reason)
        self.frontier.stop()
        return self.df.close(reason)

    def _get_requests_from_backend(self):
        if not self.frontier.manager.finished:
            info = self._get_downloader_info()
            requests = self.frontier.get_next_requests(key_type=info['key_type'], overused_keys=info['overused_keys'])
            for request in requests:
                self.enqueue_request(request)
                self.stats.inc_value('frontera/returned_requests_count')

    def _get_exception_code(self, exception):
        try:
            return exception.__class__.__name__
        except:
            return '?'

    def _get_downloader_info(self):
        downloader = self.crawler.engine.downloader
        info = {
            'key_type': 'ip' if downloader.ip_concurrency else 'domain',
            'overused_keys': []
        }
        for key, slot in downloader.slots.iteritems():
            overused_factor = len(slot.active) / float(slot.concurrency)
            if overused_factor > self.frontier.manager.settings.get('OVERUSED_SLOT_FACTOR'):
                info['overused_keys'].append(key)
        return info
