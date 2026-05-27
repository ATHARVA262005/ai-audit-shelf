import functools
import requests

def audit_log(actor: str):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            payload = {
                "actor": actor,
                "action": func.__name__,
                "params": args or kwargs
            }
            try:
                result = func(*args, **kwargs)
                payload["result"] = result
                requests.post("http://localhost:8000/api/chapters", json=payload)
                return result
            except Exception as e:
                payload["error"] = str(e)
                requests.post("http://localhost:8000/api/chapters", json=payload)
                raise e
        return wrapper
    return decorator
