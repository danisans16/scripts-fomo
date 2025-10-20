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

# GraphQL query para obtener géneros de un evento específico
GQL_EVENT_GENRES = """
query GET_EVENT_GENRES($id: ID!) {
  event(id: $id) {
    id
    title
    genres {
      name
    }
    venue {
      id
      name
    }
    startTime
    endTime
    minimumAge
    cost
  }
}
""".strip()

def gql_get_event_genres(session, event_id):
    """Obtener géneros y tiempos de un evento específico usando GraphQL"""
    headers = {
        "User-Agent": session.headers.get("User-Agent", ua()),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE,
        "Referer": f"{BASE}/events/{event_id}",
    }
    payload = {
        "operationName": "GET_EVENT_GENRES",
        "variables": {"id": str(event_id)},
        "query": GQL_EVENT_GENRES,
    }
    
    try:
        r = session.post(GQL, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            response_data = r.json()
            event_data = response_data.get("data", {}).get("event", {})
            if event_data:
                genres = event_data.get("genres", [])
                genre_names = [g.get("name", "") for g in genres if g.get("name")]
                genres_str = ", ".join(genre_names) if genre_names else ""
                
                # Extraer startTime y endTime
                start_time = event_data.get("startTime", "")
                end_time = event_data.get("endTime", "")
                
                # Extraer minimumAge
                minimum_age = event_data.get("minimumAge", "")
                
                # Extraer cost
                cost = event_data.get("cost", "")
                
                return {
                    "genres": genres_str,
                    "startTime": start_time,
                    "endTime": end_time,
                    "minimumAge": minimum_age,
                    "cost": cost
                }
        return {"genres": "", "startTime": "", "endTime": "", "minimumAge": "", "cost": ""}
    except Exception as e:
        print(f"[ERROR] GraphQL genres failed for {event_id}: {e}")
        return {"genres": "", "startTime": "", "endTime": "", "minimumAge": "", "cost": ""}

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
    
    # Buscar TODOS los elementos <li> que podrían contener tickets
    # y procesarlos en el orden exacto en que aparecen en el HTML
    all_li_elements = soup.select("li")
    
    for li in all_li_elements:
        classes = set(li.get("class") or [])
        text = li.get_text(strip=True)
        
        # Omitir elementos que claramente no son tickets
        if not text or len(text) < 3:
            continue
            
        # Procesar tickets con clases estándar
        if any(cls in classes for cls in ["onsale", "soldout", "offsale", "upcoming", "but"]):
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
        
        # Procesar tickets agotados con clase 'closed'
        elif "closed" in classes:
            # Buscar patrones de nombre y precio
            # Ejemplo: "1st release13,00 €"
            pattern = r"(.+?)(\d+[.,]\d+)\s*€"
            match = re.search(pattern, text)
            
            if match:
                title = match.group(1).strip()
                price_str = match.group(2).replace(",", ".")
                try:
                    price = float(price_str)
                    # Verificar que no sea un stopword
                    if title and not any(w in title.lower() for w in STOPWORDS):
                        out.append({"title": title, "priceRetail": price, "validType": "SOLDOUT"})
                except ValueError:
                    continue
    
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

def build_row(event, tickets, venue_name_mapping, event_time_data=None):
    event_url = event.get("contentUrl") or f"/events/{event.get('id')}"
    if event_url.startswith("/"):
        event_url = "https://ra.co" + event_url
    
    # ORDENAR TICKETS POR PRECIO de menor a mayor
    # Esto asegura que las releases más baratas aparezcan primero
    # Ej: Si la 4a release es más barata que la 2nd, aparecerá antes
    tickets_sorted_by_price = sorted(tickets, key=lambda t: (t.get("priceRetail") is None, t.get("priceRetail") or math.inf))
    
    # Mantener también una copia ordenada para currentRelease (para mantener compatibilidad)
    tickets_sorted = tickets_sorted_by_price
    
    image = pick_flyerfront_from_images(event.get("images") or [])
    if not image and event.get("flyerFront"):
        image = event["flyerFront"]

    # Usar el nombre del diccionario para el venue
    venue_name = get_venue_name_from_event(event, venue_name_mapping)

    # Usar datos de tiempo específicos del evento si están disponibles, sino fallback a date
    start_time = event_time_data.get("startTime", "") if event_time_data else ""
    end_time = event_time_data.get("endTime", "") if event_time_data else ""
    
    # Si no hay startTime/end_time, usar el campo date como fallback
    if not start_time:
        start_time = event.get("date", "")

    # Extraer minimumAge de event_time_data si está disponible
    minimum_age = event_time_data.get("minimumAge", "") if event_time_data else ""
    
    # Extraer cost de event_time_data si está disponible
    cost = event_time_data.get("cost", "") if event_time_data else ""
    
    row = {
        "venue": venue_name,  # Usar el nombre exacto del diccionario
        "eventName": event.get("title", ""),
        "url": event_url,
        "date": fmt_date_spanish(event.get("date", "")),
        "time": fmt_time_range(start_time, end_time),  # Usar startTime y endTime específicos
        "imageUrl": image or "",
        "currentRelease": pick_current_release(tickets_sorted),  # Mantener lógica original para currentRelease
        "event_date": (event.get("date", "")[:10] if event.get("date") else ""),
        "generos": event.get("generos", ""),
        "interestedCount": event.get("interestedCount", 0),  # Agregar interestedCount desde la API
        "minimumAge": minimum_age,  # Agregar edad mínima desde la API
        "cost": cost,  # Agregar coste desde la API
    }
    # USAR EL ORDEN POR PRECIO para las releases (releaseName1-6)
    # Esto asegura que las releases más baratas aparezcan primero
    for i in range(6):
        if i < len(tickets_sorted_by_price):
            t = tickets_sorted_by_price[i]
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
                    
                    # Obtener géneros y tiempos usando GraphQL
                    event_data = gql_get_event_genres(s, eid)
                    ev["generos"] = event_data.get("genres", "")  # Puede ser string vacío si no hay géneros
                    
                    if event_data.get("genres"):
                        print(f"[GENRES] {eid} → '{event_data.get('genres')}'")
                    else:
                        print(f"[GENRES] {eid} → No encontrados")
                    
                    # Mostrar información de tiempo si está disponible
                    if event_data.get("startTime") or event_data.get("endTime"):
                        start_time = event_data.get("startTime", "")
                        end_time = event_data.get("endTime", "")
                        print(f"[TIME] {eid} → {start_time} → {end_time}")
                    
                    row = build_row(ev, prices, VENUE_IDS, event_data)
                    all_rows.append(row)
                    age_info = f"Edad: {row['minimumAge']}" if row['minimumAge'] else "Edad: No especificada"
                    print(f"[OK] {eid} → '{row['eventName']}' ({len(prices)} tickets) [Géneros: {row['generos'] or 'No encontrados'}] [Time: {row['time'] or 'No time'}] [{age_info}]")
                except Exception as e:
                    print(f"[ERROR] Failed to process event {eid}: {e}")
                    # Si falla el procesamiento, intentamos con datos vacíos
                    try:
                        ev["generos"] = ""
                        prices = get_ticket_prices(s, eid)
                        row = build_row(ev, prices, VENUE_IDS, {"genres": "", "startTime": "", "endTime": "", "minimumAge": "", "cost": ""})
                        all_rows.append(row)
                        print(f"[RECOVERED] {eid} → '{row['eventName']}' ({len(prices)} tickets) [Géneros: No encontrados]")
                    except Exception as fallback_e:
                        print(f"[ERROR] Could not recover event {eid}: {fallback_e}")
                
                time.sleep(random.uniform(0.3, 0.7))  # delay optimizado para GraphQL
                
        except Exception as e:
            print(f"[ERROR] Failed to get events for {venue_name}: {e}")
            
        print()  # Separador entre venues

    import os
    # os.makedirs("output", exist_ok=True)
    out_path = "ra_venues_events.json"
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
