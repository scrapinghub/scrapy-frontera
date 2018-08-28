Frontera scheduler for Scrapy
=============================

More flexible and featured `Frontera <https://github.com/scrapinghub/frontera>`_ scheduler for scrapy, which don't force to reimplement
capabilities already present in scrapy, so it provides:

- Scrapy handled request dupefilter
- Scrapy handled disk and memory request queues
- Only send to frontera requests marked to be processed by it (using request meta attribute ``cf_store`` to True), thus avoiding lot of conflicts.
- Allows to set frontera settings from spider constructor, by loading frontera manager after spider instantiation.
- Allows frontera components to access scrapy stat manager instance by adding STATS_MANAGER frontera setting
- Better request/response converters, fully compatible with ScrapyCloud and Scrapy
- Emulates dont_filter=True scrapy Request flag
- Frontier fingerprint is same as scrapy request fingerprint (can be overriden by passing 'frontier_fingerprint' to request meta)
- Thoroughly tested, used and featured

The result is that crawler using this scheduler will not work differently than a crawler that doesn't use frontier, and
reingeneering of a spider in order to be adapted to work with frontier is minimal. 


Versions:
---------

Up to version 0.1.8, frontera==0.3.3 and python2 are required. Version 0.2 requires frontera==0.7.1 and is compatible with python3.

Usage and features:
-------------------

Note: In the context of this doc, a producer spider is the spider that writes requests to the frontier, and the consumer is the one that reads
them from the frontier. They can be either the same or separated ones.

In your project settings.py::

    SCHEDULER = 'scrapy_frontera.scheduler.FronteraScheduler'

    DOWNLOADER_MIDDLEWARES = {
        'scrapy_frontera.middlewares.SchedulerDownloaderMiddleware': 999,
    }

    SPIDER_MIDDLEWARES = {
        'scrapy_frontera.middlewares.SchedulerSpiderMiddleware': 999,
    }

    # Set to True if you want start requests to be redirected to frontier
    # By default they go directly to scrapy downloader
    # FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER = False

    # Allows to redirect to frontier, the requests with the given callback names
    # FRONTERA_SCHEDULER_REQUEST_CALLBACKS_TO_FRONTIER = []

    # Spider attributes that need to be passed to the requests redirected to frontier
    # Some previous callbacks may have generated some state needed for following ones.
    # This setting allows to transmit that state between different jobs
    # FRONTERA_SCHEDULER_STATE_ATTRIBUTES = []


Plus the usual Frontera setup. You can also set up spider specific frontera settings via the spider class attribute dict ``frontera_settings``. Example
with `hcf backend <https://github.com/scrapinghub/hcf-backend>`_::

    class MySpider(Spider):

        name = 'my-producer'

        frontera_settings = {
            'HCF_PROJECT_ID': 11111,
            'HCF_PRODUCER_FRONTIER': 'myfrontier',
            'HCF_PRODUCER_NUMBER_OF_SLOTS': 8,
        }

Scrapy-frontera also accepts the spider attribute `frontera_settings_json`. This is specially useful for consumers, which need per job
setup of reading slot.For example, you can configure a consumer spider in this way, for usage with `hcf backend <https://github.com/scrapinghub/hcf-backend>`_::

    class MySpider(Spider):

        name = 'my-consumer'

        frontera_settings = {
            'HCF_PROJECT_ID': 11111,
            'HCF_CONSUMER_FRONTIER': 'myfrontier',
        }


and invoke it via::

        scrapy crawl my-consumer -a frontera_settings_json='{"HCF_CONSUMER_SLOT": "0"}'

Settings provided through `frontera_settings_json` overrides those provided using `frontera_settings`, which in turn overrides those provided in the
project settings.py file.

Requests will go through the Frontera pipeline only if the flag ``cf_store`` with value True is included in the request meta. If ``cf_store`` is not present
or is False, requests will be processed as normal scrapy request.

Requests read from the frontier are directly enqueued by the scheduler. This means that they are not processed by spider middleware. Their
processing entrypoint is downloader middleware `process_request()` pipeline.

If requests read from frontier doesn't already have an errback defined, the scheduler will automatically assign the consumer spider `errback` method,
if it exists, to them. This is specially useful when consumer spider is not the same as the producer one.
