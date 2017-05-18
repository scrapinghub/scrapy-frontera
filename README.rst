Frontera scheduler for Scrapy
=============================

More flexible and featured `Frontera <https://github.com/scrapinghub/frontera>`_ scheduler for scrapy, which don't force to reimplement
capabilities already present in scrapy, so it provides:

- Scrapy handled request dupefilter
- Scrapy handled disk and memory request queues
- Only send to frontera requests marked to be processed by it (using request meta attribute ``cf_store`` to True), thus avoiding lot of conflicts and missing features.
- Allows to set frontera settings from spider constructor, by loading frontera manager after spider instantiation.
- Allows frontera components to access scrapy stat manager instance by adding STATS_MANAGER frontera setting
- Better request/response converters

Usage:
------

In your project settings.py::

    SCHEDULER = 'scrapy_frontera.scheduler.FronteraScheduler'

    DOWNLOADER_MIDDLEWARES = {
        'frontera.contrib.scrapy.middlewares.schedulers.SchedulerDownloaderMiddleware': 999,
    }

    SPIDER_MIDDLEWARES = {
        'frontera.contrib.scrapy.middlewares.schedulers.SchedulerSpiderMiddleware': 999,
    }

    # Set to True if you want start requests to be redirected to frontier
    # By default they go directly to scrapy downloader
    # FRONTERA_SCHEDULER_START_REQUESTS_TO_FRONTIER = False

Plus the usual Frontera setup.

Requests will go through the Frontera pipeline only if the flag ``cf_store`` with value True is included in the request meta. If ``cf_store`` is not present
or is False, requests will be processed as normal scrapy request.
