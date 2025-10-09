# pip install requests beautifulsoup4 fake-useragent
import requests, re, json, time, random, math
from datetime import datetime
from typing import List, Dict, Any
from bs4 import BeautifulSoup

BASE = "https://ra.co"
GQL  = f"{BASE}/graphql"

# =================== Venue Configuration ===================
# Diccionario de venues (id: nombre)
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

# Diccionario invertido para acceso por nombre (nombre: id)
VENUE_IDS = {name: str(vid) for vid, name in CLUB_NAMES.items()}

# =================== Helpers ===================
def ua():
    try:
        from fake_useragent import UserAgent
        return UserAgent().random
    except Exception:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": ua(), "Accept": "application/json, text/plain, */*"})
    return s

def fmt_price_eur(x):
    if x is None:
        return ""
    return f"{int(round(x))}€" if abs(x - round(x)) < 1e-6 else f"{x:.2f}".replace(".", ",") + "€"

def fmt_date_spanish(dt_iso):
    WEEK = ["LUN.", "MAR.", "MIÉ.", "JUE.", "VIE.", "SÁB.", "DOM."]
    MONTH = ["ENE.", "FEB.", "MAR.", "ABR.", "MAY.", "JUN.", "JUL.", "AGO.", "SEP.", "OCT.", "NOV.", "DIC."]
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso.replace("Z", "").split(".")[0])
        return f"{WEEK[dt.weekday()]} {dt.day:02d} {MONTH[dt.month-1]}"
    except Exception:
        return ""

def fmt_time_range(start_iso, end_iso):
    try:
        if not start_iso:
            return ""
        s = datetime.fromisoformat(start_iso.replace("Z", "").split(".")[0]).strftime("%H:%M")
        if end_iso:
            e = datetime.fromisoformat(end_iso.replace("Z", "").split(".")[0]).strftime("%H:%M")
            return f"{s} {e}"
        return s
    except Exception:
        return ""

def pick_flyerfront_from_images(images):
    if not isinstance(images, list):
        return ""
    for img in images:
        if not isinstance(img, dict):
            continue
        if (img.get("type") or "").upper() == "FLYERFRONT" and img.get("filename"):
            return img["filename"]
    for img in images:
        if isinstance(img, dict) and img.get("filename"):
            return img["filename"]
    return ""

# =================== GraphQL ===================
GQL_VENUE_EVENTS = """
query GET_VENUE_MOREON($id: ID!, $excludeEventId: ID = 0) {
  venue(id: $id) {
    id
    name
    logoUrl
    blurb
    isFollowing
    contentUrl
    events(limit: 200, type: LATEST, excludeIds: [$excludeEventId]) {
      id
      title
      interestedCount
      date
      contentUrl
      flyerFront
      queueItEnabled
      newEventForm
      images {
        id
        filename
        alt
        type
        crop
        __typename
      }
      venue {
        id
        name
        contentUrl
        live
        __typename
      }
      __typename
    }
    __typename
  }
}
""".strip()

def gql_get_events(session, venue_id, date_from=None, date_to=None, count=200):
    headers = {
        "User-Agent": session.headers.get("User-Agent", ua()),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE,
        "Referer": BASE + "/",
    }
    payload = {
        "operationName": "GET_VENUE_MOREON",
        "variables": {"id": str(venue_id), "excludeEventId": "0"},
        "query": GQL_VENUE_EVENTS,
    }
    r = session.post(GQL, headers=headers, json=payload, timeout=25)
    r.raise_for_status()
    response_data = r.json()
    
    # Extraer eventos de la respuesta
    venue_data = response_data.get("data", {}).get("venue", {})
    events = venue_data.get("events", [])
    
    print(f"[DEBUG] Total events found for venue {venue_id}: {len(events)}")
    
    # Filtrar eventos por fecha si es necesario
    if date_from and date_to:
        filtered_events = []
        for event in events:
            event_date = event.get("date", "")
            if event_date:
                # Formatear fecha del evento para comparación
                try:
                    event_date_only = event_date.split("T")[0]
                    if date_from <= event_date_only <= date_to:
                        filtered_events.append(event)
                except Exception:
                    # Si no podemos parsear la fecha, incluimos el evento
                    filtered_events.append(event)
        print(f"[DEBUG] Events after date filtering: {len(filtered_events)}")
        return filtered_events
    
    # Si no hay filtro de fechas, devolver todos los eventos
    return events

# =================== Fallback con curl/HTML ===================
def get_event_html_fallback(session, event_id):
    """Fallback: obtener HTML de la página del evento si la API falla"""
    url = f"{BASE}/events/{event_id}"
    try:
        r = session.get(url, headers={"User-Agent": ua()}, timeout=20)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"[ERROR] Fallback HTML failed for {event_id}: {e}")
    return None

def parse_event_from_html(html, event_id):
    """Parsear información básica del evento desde HTML"""
    if not html:
        return None
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Extraer información básica del HTML
    title = ""
    venue_name = ""
    date_str = ""
    image_url = ""
    
    # Título del evento
    title_el = soup.select_one("h1, .event-title, [data-testid='event-title']")
    if title_el:
        title = title_el.get_text(strip=True)
    
    # Venue
    venue_el = soup.select_one(".venue-name, [data-testid='venue-name'], .event-venue")
    if venue_el:
        venue_name = venue_el.get_text(strip=True)
    
    # Fecha
    date_el = soup.select_one(".event-date, [data-testid='event-date'], .date")
    if date_el:
        date_str = date_el.get_text(strip=True)
    
    # Imagen
    img_el = soup.select_one(".event-image img, .flyer img, [data-testid='event-image']")
    if img_el and img_el.get("src"):
        image_url = img_el["src"]
    
    return {
        "id": event_id,
        "title": title,
        "venue": {"name": venue_name, "id": ""},
        "date": date_str,
        "contentUrl": f"{BASE}/events/{event_id}",
        "images": [{"filename": image_url, "type": "FLYERFRONT"}] if image_url else [],
        "flyerFront": image_url
    }

# =================== Widget (Tickets) ===================
def get_ticket_prices(session, event_id):
    url = f"{BASE}/widget/event/{event_id}/embedtickets?backUrl=/events/{event_id}"
    r = session.get(url, headers={"User-Agent": ua()}, timeout=20)
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    if soup.select_one("#ticket-sales-ended, #no-tickets-available"):
        return []
    out = []
    STOPWORDS = {"barcode", "booking fee", "service fee", "info", "terms"}
    for li in soup.select("li.onsale, li.soldout, li.offsale, li.upcoming, li.but"):
        classes = set(li.get("class") or [])
        is_upcoming = "upcoming" in classes
        if not is_upcoming and not li.find("input", attrs={"name": "tickettypes"}):
            continue
        if   "soldout"  in classes: status = "SOLDOUT"
        elif "offsale"  in classes: status = "NOLONGERONSALE"
        elif "upcoming" in classes: status = "UPCOMING"
        else:                        status = "VALID"
        name_el = li.select_one(".pr8, .name, .title, label .pr8, .type-title")
        release = (name_el.get_text(strip=True) if name_el else "") or ""
        if not release or any(w in release.lower() for w in STOPWORDS):
            continue
        price = None
        dp = li.get("data-price")
        if dp:
            try: price = float(dp.replace(",", "."))
            except ValueError: pass
        if price is None:
            pe = li.select_one(".type-price, .price")
            if pe:
                m = re.search(r"(\d+[.,]?\d*)", pe.get_text())
                if m: price = float(m.group(1).replace(",", "."))
        out.append({"title": release, "priceRetail": price, "validType": status})
    return out

# =================== Builder ===================
def pick_current_release(tickets):
    valid = [t for t in tickets if t.get("validType") == "VALID"]
    if not valid: return ""
    valid.sort(key=lambda t: (t.get("priceRetail") is None, t.get("priceRetail")))
    return valid[0].get("title") or ""

def get_venue_name_from_event(event, venue_name_mapping):
    """Obtener el nombre del venue desde el diccionario, fallback al nombre de la API"""
    venue_info = event.get("venue", {})
    venue_id = venue_info.get("id")
    
    # Si tenemos el ID del venue, usar el nombre del diccionario
    if venue_id and int(venue_id) in CLUB_NAMES:
        return CLUB_NAMES[int(venue_id)]
    
    # Fallback: intentar encontrar por nombre
    api_venue_name = venue_info.get("name", "").lower()
    for dict_name in venue_name_mapping.keys():
        if dict_name.lower() in api_venue_name or api_venue_name in dict_name.lower():
            return dict_name
    
    # Último fallback: usar el nombre de la API
    return api_venue_name

def build_row(event, tickets, venue_name_mapping):
    event_url = event.get("contentUrl") or f"/events/{event.get('id')}"
    if event_url.startswith("/"):
        event_url = "https://ra.co" + event_url
    tickets_sorted = sorted(tickets, key=lambda t: (t.get("priceRetail") is None, t.get("priceRetail") or math.inf))
    image = pick_flyerfront_from_images(event.get("images") or [])
    if not image and event.get("flyerFront"):
        image = event["flyerFront"]

    # Usar el nombre del diccionario para el venue
    venue_name = get_venue_name_from_event(event, venue_name_mapping)

    row = {
        "venue": venue_name,  # Usar el nombre exacto del diccionario
        "eventName": event.get("title", ""),
        "url": event_url,
        "date": fmt_date_spanish(event.get("date", "")),
        "time": fmt_time_range(event.get("date", ""), ""),
        "imageUrl": image or "",
        "currentRelease": pick_current_release(tickets_sorted),
        "event_date": (event.get("date", "")[:10] if event.get("date") else ""),
        "generos": "",
    }

    for i in range(6):
        if i < len(tickets_sorted):
            t = tickets_sorted[i]
            title = (t.get("title") or "").strip()
            st = (t.get("validType") or "").upper()
            if st in ("SOLDOUT", "NOLONGERONSALE"):
                title = f"{title} - Agotado"
            row[f"releaseName{i+1}"] = title
            row[f"price{i+1}"] = fmt_price_eur(t.get("priceRetail"))
            row[f"releaseUrl{i+1}"] = event_url
        else:
            row[f"releaseName{i+1}"] = ""
            row[f"price{i+1}"] = ""
            row[f"releaseUrl{i+1}"] = ""

    return row

# =================== Main ===================
if __name__ == "__main__":
    # Opción 1: Obtener TODOS los eventos (sin filtro de fechas)
    DATE_FROM = None
    DATE_TO = None
    # Opción 2: Filtrar por fechas específicas (descomenta las siguientes líneas)
    # DATE_FROM = "2025-10-09"
    # DATE_TO = "2025-10-12"
    COUNT = 200

    s = make_session()

    if DATE_FROM and DATE_TO:
        print(f"[START] Extrayendo eventos de {len(CLUB_NAMES)} venues ({DATE_FROM}→{DATE_TO})...")
    else:
        print(f"[START] Extrayendo TODOS los eventos de {len(CLUB_NAMES)} venues...")
    print(f"[INFO] Venues: {', '.join(CLUB_NAMES.values())}\n")

    all_rows = []
    
    for venue_id, venue_name in CLUB_NAMES.items():
        print(f"[PROCESSING] Venue: {venue_name} (ID: {venue_id})")
        
        try:
            # Intentar obtener eventos via API GraphQL
            events = gql_get_events(s, venue_id, DATE_FROM, DATE_TO, COUNT)
            
            if not events:
                print(f"[WARNING] No events found for {venue_name} via API")
                continue
                
            print(f"[INFO] Found {len(events)} events for {venue_name}")
            
            for ev in events:
                eid = ev["id"]
                try:
                    prices = get_ticket_prices(s, eid)
                    row = build_row(ev, prices, VENUE_IDS)
                    all_rows.append(row)
                    print(f"[OK] {eid} → '{row['eventName']}' ({len(prices)} tickets)")
                except Exception as e:
                    print(f"[ERROR] Failed to process event {eid}: {e}")
                    # Intentar fallback con HTML
                    try:
                        html = get_event_html_fallback(s, eid)
                        if html:
                            event_fallback = parse_event_from_html(html, eid)
                            if event_fallback:
                                prices = get_ticket_prices(s, eid)
                                row = build_row(event_fallback, prices, VENUE_IDS)
                                all_rows.append(row)
                                print(f"[FALLBACK OK] {eid} → '{row['eventName']}' (HTML parsed)")
                    except Exception as fallback_e:
                        print(f"[FALLBACK ERROR] Could not parse HTML for {eid}: {fallback_e}")
                
                time.sleep(random.uniform(1.0, 2.0))  # delay para RA
                
        except Exception as e:
            print(f"[ERROR] Failed to get events for {venue_name}: {e}")
            
        print()  # Separador entre venues

    import os
    os.makedirs("output", exist_ok=True)
    out_path = "output/ra_venues_events.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Guardadas {len(all_rows)} filas en {out_path}")
    
    # Resumen por venue
    venue_summary = {}
    for row in all_rows:
        venue = row["venue"]
        venue_summary[venue] = venue_summary.get(venue, 0) + 1
    
    print("\n📊 Resumen por venue:")
    for venue, count in sorted(venue_summary.items()):
        print(f"  {venue}: {count} eventos")
