"""One inference/template operation at a time in the single device process."""
from functools import wraps
from threading import RLock

_inference_lock = RLock()


def serialized_inference(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with _inference_lock:
            return function(*args, **kwargs)
    return guarded
