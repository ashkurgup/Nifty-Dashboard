import redis, json, time

pool = redis.ConnectionPool(host="127.0.0.1", port=6379, decode_responses=True, max_connections=20)
_r = redis.Redis(connection_pool=pool)

def get(key, default=None):
    val = _r.get(key)
    return val if val else default

def set(key, value, ex=None):
    return _r.set(key, value, ex=ex)

def get_json(key, default):
    try:
        raw = _r.get(key)
        return json.loads(raw) if raw else default
    except: return default

def set_json(key, obj, ex=None):
    return _r.set(key, json.dumps(obj), ex=ex)

def queue_push(queue, data):
    _r.lpush(queue, json.dumps(data))

def queue_pop(queue, timeout=5):
    job = _r.brpop(queue, timeout=timeout)
    return json.loads(job[1]) if job else None

def heartbeat(key, ttl=30):
    _r.set(key, int(time.time()), ex=ttl)
