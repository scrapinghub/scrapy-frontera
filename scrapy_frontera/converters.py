import uuid

import logging

from scrapy.http.request import Request as ScrapyRequest
from scrapy.http.response import Response as ScrapyResponse
from scrapy.utils.request import request_fingerprint

from frontera.core.models import Request as FrontierRequest
from frontera.core.models import Response as FrontierResponse
from frontera.utils.converters import BaseRequestConverter, BaseResponseConverter


_LOG = logging.getLogger(__name__)


class RequestConverter(BaseRequestConverter):
    """Converts between frontera and Scrapy request objects"""
    def __init__(self, spider):
        self.spider = spider

    def to_frontier(self, scrapy_request):
        """request: Scrapy > Frontier"""
        if isinstance(scrapy_request.cookies, dict):
            cookies = scrapy_request.cookies
        else:
            cookies = dict(sum([d.items() for d in scrapy_request.cookies], []))
        cb = scrapy_request.callback
        if callable(cb):
            cb = _find_method(self.spider, cb)
        eb = scrapy_request.errback
        if callable(eb):
            eb = _find_method(self.spider, eb)

        statevars = self.spider.crawler.settings.getlist('FRONTERA_SCHEDULER_STATE_ATTRIBUTES', [])
        meta = {
            'scrapy_callback': cb,
            'scrapy_errback': eb,
            'scrapy_meta': scrapy_request.meta,
            'scrapy_body': scrapy_request.body,
            'spider_state': [(attr, getattr(self.spider, attr, None)) for attr in statevars],
            'origin_is_frontier': True,
        }

        fingerprint_scrapy_request = scrapy_request
        if fingerprint_scrapy_request.dont_filter:
            # if dont_filter is True, we need to simulate
            # not filtering by generating a different fingerprint each time we see same request.
            # So let's altere randomly the url
            fake_url = fingerprint_scrapy_request.url + str(uuid.uuid4())
            fingerprint_scrapy_request = fingerprint_scrapy_request.replace(url=fake_url)
        meta['frontier_fingerprint'] = scrapy_request.meta.get('frontier_fingerprint',
                                       request_fingerprint(fingerprint_scrapy_request))
        return FrontierRequest(url=scrapy_request.url,
                               method=scrapy_request.method,
                               headers=scrapy_request.headers,
                               cookies=cookies,
                               meta=meta)

    def from_frontier(self, frontier_request):
        """request: Frontier > Scrapy"""
        cb = frontier_request.meta.get('scrapy_callback', None)
        if cb and self.spider:
            cb = _get_method(self.spider, cb)
        eb = frontier_request.meta.get('scrapy_errback', None)
        if eb and self.spider:
            eb = _get_method(self.spider, eb)
        body = frontier_request.meta.get('scrapy_body', None)
        meta = frontier_request.meta['scrapy_meta']
        meta['frontier_request'] = frontier_request

        for attr, val in frontier_request.meta.get('spider_state', []):
            prev_value = getattr(self.spider, attr, None)
            if prev_value is not None and prev_value != val:
                _LOG.error("State for attribute '%s' changed from %s to %s by request <%s> so crawl may loose consistency. \
                           Per request state should be propagated through request meta.", attr, prev_value, val, frontier_request.url)
            else:
                setattr(self.spider, attr, val)

        return ScrapyRequest(url=frontier_request.url,
                             callback=cb,
                             errback=eb,
                             body=body,
                             method=frontier_request.method,
                             headers=frontier_request.headers,
                             cookies=frontier_request.cookies,
                             meta=meta,
                             dont_filter=True)


class ResponseConverter(BaseResponseConverter):
    """Converts between frontera and Scrapy response objects"""
    def __init__(self, spider, request_converter):
        self.spider = spider
        self._request_converter = request_converter

    def to_frontier(self, scrapy_response):
        """response: Scrapy > Frontier"""
        frontier_request = scrapy_response.meta.get('frontier_request',
                self._request_converter.to_frontier(scrapy_response.request))
        frontier_request.meta['scrapy_meta'] = scrapy_response.meta
        return FrontierResponse(url=scrapy_response.url,
                                status_code=scrapy_response.status,
                                headers=scrapy_response.headers,
                                body=scrapy_response.body,
                                request=frontier_request)

    def from_frontier(self, response):
        """response: Frontier > Scrapy"""
        return ScrapyResponse(url=response.url,
                              status=response.status_code,
                              headers=response.headers,
                              body=response.body,
                              request=self._request_converter.from_frontier(response.request))


def _find_method(obj, func):
    if obj and hasattr(func, 'im_self') and func.im_self is obj:
        return func.im_func.__name__
    else:
        raise ValueError("Function %s is not a method of: %s" % (func, obj))


def _get_method(obj, name):
    name = str(name)
    try:
        return getattr(obj, name)
    except AttributeError:
        raise ValueError("Method %r not found in: %s" % (name, obj))
