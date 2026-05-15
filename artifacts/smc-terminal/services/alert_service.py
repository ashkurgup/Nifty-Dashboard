# services/alert_service.py

from infra import redis_bus as rbus

REDIS_ALERTS = "active_alerts"


def add_alert(alert: dict):
    try:
        alerts = rbus.get_json(REDIS_ALERTS, [])

        # ✅ prevent duplicates
        alerts = [a for a in alerts if a.get("id") != alert.get("id")]

        alerts.append(alert)

        rbus.set_json(REDIS_ALERTS, alerts)

    except Exception as e:
        print(f"[ALERT ADD ERROR] {e}")


def remove_alert(alert_id):
    try:
        alerts = rbus.get_json(REDIS_ALERTS, [])
        alerts = [a for a in alerts if str(a.get("id")) != str(alert_id)]
        rbus.set_json(REDIS_ALERTS, alerts)

    except Exception as e:
        print(f"[ALERT REMOVE ERROR] {e}")


def get_alerts():
    return rbus.get_json(REDIS_ALERTS, [])


def check_alerts(symbol: str, ltp: float):
    try:
        alerts = rbus.get_json(REDIS_ALERTS, [])
        remaining = []

        for a in alerts:
            try:
                if a.get("index") != symbol:
                    remaining.append(a)
                    continue

                target = float(a.get("target", 0))

                triggered = False

                # ✅ AUTO direction detection
                base = float(a.get("base_price", target))

                if ltp >= target and base <= target:
                    triggered = True
                elif ltp <= target and base >= target:
                    triggered = True

                if triggered:
                    rbus.queue_push("alert_queue", a)
                else:
                    a["ltp"] = ltp  # ✅ keep UI updated
                    remaining.append(a)

            except Exception as e:
                print(f"[ALERT CHECK ERROR] {e}")
                remaining.append(a)

        rbus.set_json(REDIS_ALERTS, remaining)

    except Exception as e:
        print(f"[ALERT ENGINE ERROR] {e}")
