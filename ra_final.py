import os, re, json, time, random, sys, math
from datetime import datetime
from typing import List, Dict, Any
from unidecode import unidecode
from botasaurus.browser import browser, Driver
from botasaurus.soupify import soupify

# ========= Config =========
CLUB_IDS = [911, 150612, 195409, 3818, 3760, 60710, 2072, 2253, 216950]

MAX_EVENTS_PER_CLUB = 100
HEADLESS = False  # pon True cuando esté estable

CLUB_NAMES = {
    911: 'Razzmatazz',
    150612: 'M7 CLUB',
    195409: 'Les Enfants',
    3818: 'Macarena Club',
    3760: 'La Terrazza',
    60710: 'Input',
    2072: 'Nitsa',
    2253: 'Moog',
    216950: 'Noxe'
}

def log(*args):
    print(*args); sys.stdout.flush()

def sleep_jitter(ms_min=500, ms_max=900):
    time.sleep(random.uniform(ms_min/1000.0, ms_max/1000.0))

# ========= Formato fecha/hora/precio =========
WEEK = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
MONTH = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEPT", "OCT", "NOV", "DIC"]

def fmt_fecha_label(dt_iso: str) -> str:
    if not dt_iso: return ""
    try:
        dt = datetime.fromisoformat(dt_iso.replace("Z","").split(".")[0])
        return f"{WEEK[dt.weekday()]}, {dt.day:02d} {MONTH[dt.month-1]}"
    except Exception:
        return ""

def fmt_date_spanish(dt_iso: str) -> str:
    # Para el JSON de precios (estilo "MIÉ. 24 SEP.")
    WEEK2 = ["LUN.", "MAR.", "MIÉ.", "JUE.", "VIE.", "SÁB.", "DOM."]
    MONTH2 = ["ENE.", "FEB.", "MAR.", "ABR.", "MAY.", "JUN.", "JUL.", "AGO.", "SEP.", "OCT.", "NOV.", "DIC."]
    if not dt_iso: return ""
    try:
        dt = datetime.fromisoformat(dt_iso.replace("Z","").split(".")[0])
        return f"{WEEK2[dt.weekday()]} {dt.day:02d} {MONTH2[dt.month-1]}"
    except Exception:
        return ""

def fmt_hora_label(start_iso: str, end_iso: str) -> str:
    def clock(x):
        return datetime.fromisoformat(x.replace("Z","").split(".")[0]).strftime("%I:%M %p")
    try:
        if start_iso and end_iso:
            return f"{clock(start_iso)} - {clock(end_iso)}"
        return clock(start_iso) if start_iso else ""
    except Exception:
        return ""

def fmt_time_range(start_iso: str, end_iso: str) -> str:
    # Para el JSON de precios (24h "HH:MM HH:MM")
    try:
        if not start_iso: return ""
        s = datetime.fromisoformat(start_iso.replace("Z","").split(".")[0]).strftime("%H:%M")
        if end_iso:
            e = datetime.fromisoformat(end_iso.replace("Z","").split(".")[0]).strftime("%H:%M")
            return f"{s} {e}"
        return s
    except Exception:
        return ""

def fmt_price_eur(x: Any) -> str:
    if x is None: return ""
    if isinstance(x, (int, float)):
        if abs(x - round(x)) < 1e-6:
            return f"{int(round(x))}€"
        return f"{x:.2f}".replace(".", ",") + "€"
    return ""

def slugify(txt: str) -> str:
    s = unidecode((txt or "").lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

# ========= Parsers HTML =========
def extract_event_ids_from_club_html(html: str) -> List[str]:
    ids = re.findall(r'/events/(\d+)', html)
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out

def extract_jsonld(soup) -> Dict[str, Any]:
    node = soup.select_one('script[type="application/ld+json"]')
    if not node:
        return {}
    try:
        data = json.loads(node.text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def extract_og_image(soup) -> str:
    og = soup.select_one('meta[property="og:image"]')
    return og.get("content") if og and og.get("content") else ""

def extract_genres_from_html(soup) -> str:
    gens = []
    for a in soup.select('a[href*="/genre/"]'):
        txt = (a.get_text(" ", strip=True) or "").strip()
        if txt and txt.lower() not in [g.lower() for g in gens]:
            gens.append(txt)
    return ", ".join(gens)

def find_script_blocks(html: str) -> List[str]:
    return re.findall(r"<script[^>]*>([\s\S]*?)</script>", html, flags=re.I)

def extract_ticket_objects(script_text: str) -> List[Dict[str, Any]]:
    out = []
    idx = 0
    while True:
        m = re.search(r'"__typename"\s*:\s*"Ticket"', script_text[idx:])
        if not m: break
        anchor = idx + m.start()
        start = anchor
        while start > 0 and script_text[start] != "{": start -= 1
        brace, end, ok = 0, start, False
        while end < len(script_text):
            ch = script_text[end]
            if ch == "{": brace += 1
            elif ch == "}":
                brace -= 1
                if brace == 0:
                    ok = True
                    break
            end += 1
        if ok:
            candidate = script_text[start:end+1]
            try:
                obj = json.loads(candidate)
                if obj.get("__typename") == "Ticket":
                    out.append(obj)
            except Exception:
                try:
                    obj = json.loads(bytes(candidate, "utf-8").decode("unicode_escape"))
                    if obj.get("__typename") == "Ticket":
                        out.append(obj)
                except Exception:
                    pass
        idx = end + 1
    return out

def pick_current_release(tickets_norm: List[Dict[str, Any]]) -> str:
    valid = [t for t in tickets_norm if t.get("status") == "VALID" and not t.get("isAddOn")]
    if not valid: return ""
    valid.sort(key=lambda t: (t.get("price") is None, t.get("price")))
    return valid[0].get("title") or ""

# ========= Construcción de salidas =========
def build_event_card(club_name: str, event_url: str, soup, page_html: str) -> Dict[str, Any]:
    j = extract_jsonld(soup)
    title = j.get("name") or (soup.select_one("h1").get_text(strip=True) if soup.select_one("h1") else "")
    start = j.get("startDate", "")
    end   = j.get("endDate", "")
    image = ""
    if isinstance(j.get("image"), list) and j["image"]:
        image = j["image"][0]
    if not image:
        image = extract_og_image(soup)
    generos = extract_genres_from_html(soup)

    return {
        "disco": club_name,
        "evento": title or "",
        "fecha": fmt_fecha_label(start),
        "url_evento": event_url,
        "generos": generos,
        "hora": fmt_hora_label(start, end),
        "url_imagen": image or ""
    }, j  # devolvemos también el JSON-LD para el precio JSON

def build_price_entry(event_url: str, meta: Dict[str, Any], page_html: str) -> Dict[str, Any]:
    # tickets
    tickets_raw = []
    for sc in find_script_blocks(page_html):
        tickets_raw.extend(extract_ticket_objects(sc))
    tickets_norm = [{
        "title": t.get("title"),
        "price": t.get("priceRetail"),
        "status": t.get("validType"),
        "isAddOn": t.get("isAddOn", False),
        "url": t.get("url") or ""  # RA no suele exponerla; quedará vacío
    } for t in tickets_raw]
    tickets_norm.sort(key=lambda x: (x.get("price") is None, x.get("price") if x.get("price") is not None else math.inf))

    # meta
    venue_name = ""
    loc = meta.get("location") if isinstance(meta, dict) else None
    if isinstance(loc, dict):
        venue_name = loc.get("name") or ""
    event_name = meta.get("name", "")
    start = meta.get("startDate", "")
    end   = meta.get("endDate", "")
    image = ""
    if isinstance(meta.get("image"), list) and meta["image"]:
        image = meta["image"][0]

    out = {
        "venue": slugify(venue_name) if venue_name else "",
        "eventName": event_name or "",
        "url": event_url,
        "date": fmt_date_spanish(start),
        "time": fmt_time_range(start, end),
        "imageUrl": image or "",
        "currentRelease": pick_current_release(tickets_norm),
        "event_date": (start or "")[:10],
    }

    # Relleno 1..6: si la release existe, releaseUrl = t.url or event_url; si no existe, todo vacío
    for i in range(6):
        if i < len(tickets_norm):
            t = tickets_norm[i]
            out[f"releaseName{i+1}"] = t.get("title") or ""
            out[f"price{i+1}"] = fmt_price_eur(t.get("price"))
            out[f"releaseUrl{i+1}"] = (t.get("url") or event_url)
        else:
            out[f"releaseName{i+1}"] = ""
            out[f"price{i+1}"] = ""
            out[f"releaseUrl{i+1}"] = ""
    return out


def looks_like_verification(html: str) -> bool:
    h = (html or "").lower()
    strong = [
        "attention required!",
        "just a moment...",
        "hcaptcha",
        "data-sitekey",
        "cf-chl-",
        "why did this happen?"
    ]
    return any(s in h for s in strong)

# ========= Scraper de UN club =========
@browser(
    headless=HEADLESS,
    block_images_and_css=True,
    reuse_driver=False,
    raise_exception=True,
    cache=False
)
def scrape_club(driver: Driver, data: dict):
    club_id    = int(data.get("club_id"))
    max_events = int(data.get("max_events", MAX_EVENTS_PER_CLUB))
    club_name  = CLUB_NAMES.get(club_id, "Unknown Club")

    # 1) Página del club
    club_url = f"https://es.ra.co/clubs/{club_id}/events"
    driver.short_random_sleep()
    driver.get(club_url)
    driver.short_random_sleep()

    html = driver.page_html
    if looks_like_verification(html):
        log(f"[BLOQUEO] Verificación en club {club_id}")
        return {"club_id": club_id, "events": [], "prices": [], "error": "verification"}

    ids = extract_event_ids_from_club_html(html)
    if not ids:
        log(f"[WARN] No se encontraron eventIds en club {club_id}.")
        return {"club_id": club_id, "events": [], "prices": []}

    log(f"[INFO] Club {club_id} ({club_name}) → {len(ids)} eventIds (hasta {max_events})")

    events_out: List[Dict[str, Any]] = []
    prices_out: List[Dict[str, Any]] = []

    # 2) Eventos
    for ev_id in ids[:max_events]:
        event_url = f"https://es.ra.co/events/{ev_id}"
        try:
            driver.get(event_url)
            driver.short_random_sleep()

            # parsear
            for attempt in range(5):
                page_html = driver.page_html
                soup = soupify(driver)
                # tarjeta evento + JSON-LD para precios
                card, meta = build_event_card(club_name, event_url, soup, page_html)
                if card["evento"] or meta.get("startDate") or meta.get("endDate"):
                    events_out.append(card)
                    # entrada de precios en archivo separado
                    prices_out.append(build_price_entry(event_url, meta, page_html))
                    log(f"[OK] {ev_id} → '{card['evento']}'")
                    break
                time.sleep(0.5 + random.random()*0.6)

            sleep_jitter(600, 1000)

        except Exception as e:
            log(f"[ERR] {ev_id} → {e}")
            sleep_jitter(900, 1400)
            continue

    log(f"[DONE] Club {club_id}: eventos {len(events_out)}, precios {len(prices_out)}")
    return {"club_id": club_id, "events": events_out, "prices": prices_out}

# ========= Orquestador multi-club =========
def run_all_clubs(club_ids: List[int], max_events_per_club: int):
    all_events: List[Dict[str, Any]] = []
    all_prices: List[Dict[str, Any]] = []
    seen_event_urls = set()  # dedup global por url_evento

    for cid in club_ids:
        res = scrape_club({"club_id": cid, "max_events": max_events_per_club})

        chunks_events, chunks_prices = [], []
        if isinstance(res, dict):
            chunks_events = res.get("events", [])
            chunks_prices = res.get("prices", [])
        elif isinstance(res, list):
            for item in res:
                if isinstance(item, dict):
                    chunks_events.extend(item.get("events", []))
                    chunks_prices.extend(item.get("prices", []))

        # merge con dedup por url_evento / url
        added_e, added_p = 0, 0
        # Eventos
        for ev in chunks_events:
            url = ev.get("url_evento")
            if url and url not in seen_event_urls:
                seen_event_urls.add(url)
                all_events.append(ev)
                added_e += 1
        # Precios (alineados por url)
        for pr in chunks_prices:
            url = pr.get("url")
            if url and url in seen_event_urls:
                all_prices.append(pr)
                added_p += 1

        log(f"[MERGE] Club {cid}: +{added_e} eventos, +{added_p} precios → totales: {len(all_events)} / {len(all_prices)}")
        sleep_jitter(1200, 1800)

    return all_events, all_prices

# ========= Main =========
if __name__ == "__main__":
    events, prices = run_all_clubs(CLUB_IDS, MAX_EVENTS_PER_CLUB)
    os.makedirs("output", exist_ok=True)

    events_path = "output/ra_all_events.json"
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    prices_path = "output/ra_prices.json"
    with open(prices_path, "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Guardados {len(events)} eventos en {events_path}")
    print(f"✅ Guardados {len(prices)} bloques de precios en {prices_path}")
