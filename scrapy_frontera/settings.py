from .utils.backend import cf_make_request

DEFAULT_SETTINGS = {
    'MIDDLEWARES': ['scrapy_frontera.components.fingerprint.UrlFingerprintMiddleware'],
    'FRONTERA_MAKE_REQUEST': cf_make_request,
}
