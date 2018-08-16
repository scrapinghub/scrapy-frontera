def cf_make_request(fp, qdata, frontera_request_cls):
    """ 
    Build frontera request from qdata and request fingerprint (usually the url)
    """
    url = qdata.pop('url', fp) 
    kwargs = qdata.pop('request', {}) 
    if qdata:
        kwargs.setdefault('meta', {}) 
        kwargs['meta'].setdefault('scrapy_meta', {}) 
        kwargs['meta']['scrapy_meta']['qdata'] = qdata
    return frontera_request_cls(url, **kwargs)
