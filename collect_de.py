"""
Сбор цен по станциям Германии (Tankerkoenig / MTS-K).

Ограничение API: 1 запрос в минуту. Один запрос отдаёт ВСЕ станции
в радиусе -- значит, панель высокого разрешения строится одним
запросом раз в несколько минут.

Стратегия: один запуск работает ~55 минут, опрашивая раз в 5 минут.
Запускается по расписанию каждый час. Итого ~288 снимков в сутки.

Настройка (переменные окружения):
  TK_APIKEY   -- ключ API
  TK_LAT      -- широта центра
  TK_LNG      -- долгота центра
  TK_RAD      -- радиус в км (макс. 25)

ВАЖНО про выбор точки: нужен участок, где несколько станций
реально конкурируют друг с другом. Радиус 2-4 км по городу,
а не 25 -- иначе в выборку попадут станции, которые друг о друге
знать не знают.
"""

import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

import re

def _clean(name, default=""):
    v = os.environ.get(name, default) or default
    return re.sub(r"\s+", "", v)

APIKEY = _clean("TK_APIKEY")
LAT = _clean("TK_LAT", "52.5200")
LNG = _clean("TK_LNG", "13.4050")
RAD = _clean("TK_RAD", "3")

print(f"[проверка] LAT={LAT!r} LNG={LNG!r} RAD={RAD!r}")
BASE = "https://creativecommons.tankerkoenig.de/json/list.php"
INTERVAL = 90          # секунд между опросами
DURATION = 5 * 60 * 60      # пять часов 

import uuid
RUN_ID = os.environ.get("GITHUB_RUN_ID", uuid.uuid4().hex[:8])
DAY = datetime.now(timezone.utc).strftime("%Y%m%d")
RAW_DIR = "data/de_raw"
CSV_PATH = f"data/parts/de_{DAY}_{RUN_ID}.csv"
FIELDS = ["ts", "id", "brand", "name", "place", "lat", "lng",
          "dist", "e5", "e10", "diesel", "isOpen"]


def fetch():
    url = (f"{BASE}?lat={LAT}&lng={LNG}&rad={RAD}"
           f"&sort=dist&type=all&apikey={APIKEY}")
    req = urllib.request.Request(
        url, headers={"User-Agent": "student-research-project"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def parse(text, ts):
    data = json.loads(text)
    if not data.get("ok", False):
        raise RuntimeError(f"API вернул ошибку: {data.get('message')}")
    rows = []
    for s in data.get("stations", []):
        rows.append({
            "ts": ts,
            "id": s.get("id"),
            "brand": s.get("brand"),
            "name": s.get("name"),
            "place": s.get("place"),
            "lat": s.get("lat"),
            "lng": s.get("lng"),
            "dist": s.get("dist"),
            "e5": s.get("e5"),
            "e10": s.get("e10"),
            "diesel": s.get("diesel"),
            "isOpen": s.get("isOpen"),
        })
    return rows


def append(rows):
    os.makedirs("data/parts", exist_ok=True)
    new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def main():
    if not APIKEY:
        print("Не задан TK_APIKEY", file=sys.stderr)
        sys.exit(1)

    os.makedirs(RAW_DIR, exist_ok=True)
    start = time.time()
    n_ok = n_fail = 0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_path = f"{RAW_DIR}/{day}_{RUN_ID}.jsonl"

    print(f"Точка: {LAT}, {LNG}, радиус {RAD} км")
    print(f"Опрос раз в {INTERVAL} с в течение {DURATION // 60} мин\n")

    while time.time() - start < DURATION:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            text = fetch()
            # сырое сохраняем ВСЕГДА -- разбор можно починить, данные нет
            with open(raw_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": ts, "body": text},
                                   ensure_ascii=False) + "\n")
            rows = parse(text, ts)
            append(rows)
            n_ok += 1
            print(f"  {ts}  станций: {len(rows)}")
        except urllib.error.HTTPError as e:
            n_fail += 1
            print(f"  {ts}  HTTP {e.code}", file=sys.stderr)
        except Exception as e:
            n_fail += 1
            print(f"  {ts}  ошибка: {e}", file=sys.stderr)

        remaining = DURATION - (time.time() - start)
        if remaining <= INTERVAL:
            break
        time.sleep(INTERVAL)

    print(f"\nУспешных опросов: {n_ok}, неудачных: {n_fail}")
    if n_ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
