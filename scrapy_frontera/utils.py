def get_callback_name(request):
    if request.callback is None:
        return "parse"
    if hasattr(request.callback, "__func__"):
        return request.callback.__func__.__name__
    return None
