import json
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

    def is_frontera_request(self, request):
        """
        Only requests which its callback is the spider can be sent
        """
        if request.meta.get('cf_store', False) or request.callback is not None and \
                hasattr(request.callback, '__func__') and request.callback.__func__.__name__ in \
                self.frontier_requests_callbacks:
            if request.callback is None or getattr(request.callback, '__self__', None) is self.spider:
                return True
            raise ValueError('Request <{}>: frontera request callback must be a spider method.'.format(request))
        return False

    def process_spider_output(self, response, result, spider):
        links = []
        for element in result:
            if isinstance(element, Request) and self.is_frontera_request(element):
                links.append(element)
            else:
                yield element
        self.frontier.page_crawled(response)
        if links:
            self.frontier.links_extracted(response.request, links)
            self.stats.inc_value('frontera/links_extracted_count', len(links))

    def process_exception(self, request, exception, spider):
        error_code = self._get_exception_code(exception)
        if self.is_frontera_request(request):
            self.frontier.request_error(request=request, error=error_code)

    def open(self, spider):
        super(FronteraScheduler, self).open(spider)
        settings = ScrapySettingsAdapter(spider.crawler.settings)
        settings.set_from_dict(getattr(spider, 'frontera_settings', {}))
        settings.set_from_dict(json.loads(getattr(spider, 'frontera_settings_json', '{}')))
        settings.set('STATS_MANAGER', self.stats)
        self.frontier = ScrapyFrontierManager(settings)

        self.frontier.set_spider(spider)

        if self.crawler.settings.getbool('FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER'):
            self.frontier.add_seeds(spider.start_requests())

        self.frontier_requests_callbacks = \
            self.crawler.settings.getlist('FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER')

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
                if request.errback is None and hasattr(self.spider, 'errback'):
                    request.errback = self.spider.errback
                    request.callback = request.callback or self.spider.parse
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
        for key, slot in downloader.slots.items():
            overused_factor = len(slot.active) / float(slot.concurrency)
            if overused_factor > self.frontier.manager.settings.get('OVERUSED_SLOT_FACTOR'):
                info['overused_keys'].append(key)
        return info
