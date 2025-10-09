# pip install botasaurus beautifulsoup4 unidecode fake-useragent concurrent.futures
import os, re, json, time, random, sys, math
from datetime import datetime
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from unidecode import unidecode
from botasaurus.browser import browser, Driver
from botasaurus.soupify import soupify
from fake_useragent import UserAgent

# ========= Config =========
CLUB_IDS = [911, 150612, 195409, 3818, 3760, 60710, 2072, 2253, 216950]
MAX_EVENTS_PER_CLUB = 30  # Reducido para menor impacto
HEADLESS = False  # Modo gráfico para evitar detección en headless

# Configuración anti-detección máxima discreción
USE_ROTATING_PROXIES = False  # Cambiar a True si tienes proxies
PROXY_LIST = []  # Añadir tus proxies aquí: ["http://user:pass@ip:port", ...]
MAX_RETRIES = 1  # Reducido para evitar sospechas
HUMAN_DELAY_MIN = 2000  # ms - Aumentado significativamente
HUMAN_DELAY_MAX = 5000  # ms - Aumentado significativamente

# Configuración de paralelización desactivada para máxima discreción
ENABLE_PARALLEL = False
MAX_WORKERS = 1  # Totalmente secuencial

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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {' '.join(map(str, args))}")
    sys.stdout.flush()

def sleep_jitter(ms_min=500, ms_max=900):
    """Sleep aleatorio para simular comportamiento humano"""
    sleep_time = random.uniform(ms_min/1000.0, ms_max/1000.0)
    time.sleep(sleep_time)

def human_delay(min_ms=None, max_ms=None):
    """Delay más largo para simular comportamiento humano natural"""
    min_delay = min_ms or HUMAN_DELAY_MIN
    max_delay = max_ms or HUMAN_DELAY_MAX
    sleep_jitter(min_delay, max_delay)

def get_random_user_agent():
    """Obtener un User Agent aleatorio"""
    try:
        ua = UserAgent()
        return ua.random
    except:
        # Fallback a User Agents comunes si falla fake-useragent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        return random.choice(user_agents)

def get_random_proxy():
    """Obtener un proxy aleatorio de la lista"""
    if USE_ROTATING_PROXIES and PROXY_LIST:
        return random.choice(PROXY_LIST)
    return None

# ========= Formato fecha/hora/precio =========
WEEK = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
MONTH = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEPT", "OCT", "NOV", "DIC"]

def fmt_date_spanish(dt_iso: str) -> str:
    # "MIÉ. 24 SEP."
    WEEK2 = ["LUN.", "MAR.", "MIÉ.", "JUE.", "VIE.", "SÁB.", "DOM."]
    MONTH2 = ["ENE.", "FEB.", "MAR.", "ABR.", "MAY.", "JUN.", "JUL.", "AGO.", "SEP.", "OCT.", "NOV.", "DIC."]
    if not dt_iso: return ""
    try:
        dt = datetime.fromisoformat(dt_iso.replace("Z","").split(".")[0])
        return f"{WEEK2[dt.weekday()]} {dt.day:02d} {MONTH2[dt.month-1]}"
    except Exception:
        return ""

def fmt_time_range(start_iso: str, end_iso: str) -> str:
    # "HH:MM HH:MM" en 24h
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

# ========= Construcción de la entrada final (precios + generos) =========
def build_price_row(event_url: str, page_html: str, meta: Dict[str, Any], generos: str) -> Dict[str, Any]:
    # Tickets desde los <script> del HTML
    tickets_raw = []
    for sc in find_script_blocks(page_html):
        tickets_raw.extend(extract_ticket_objects(sc))
    tickets_norm = [{
        "title": t.get("title"),
        "price": t.get("priceRetail"),
        "status": t.get("validType"),         # p.ej., VALID, SOLDOUT, NOLONGERONSALE
        "isAddOn": t.get("isAddOn", False),
        "url": t.get("url") or ""             # normalmente vacío
    } for t in tickets_raw]
    tickets_norm.sort(key=lambda x: (x.get("price") is None, x.get("price") if x.get("price") is not None else math.inf))

    # Meta
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
    if not image:
        # fallback: intentar og:image (si necesitas, podrías pasar también soup)
        pass

    # Base
    out = {
        "venue": slugify(venue_name) if venue_name else "",
        "eventName": event_name or "",
        "url": event_url,
        "date": fmt_date_spanish(start),
        "time": fmt_time_range(start, end),
        "imageUrl": image or "",
        "currentRelease": pick_current_release(tickets_norm),
        "event_date": (start or "")[:10],
        "generos": generos or "",     # <- añadido
    }

    # Releases 1..6 (si existe → url = release.url o event_url; si no existe → campos vacíos)
    for i in range(6):
        if i < len(tickets_norm):
            t = tickets_norm[i]
            # etiqueta "Agotado" si status indica sold out / no disponible
            title = (t.get("title") or "").strip()
            status = (t.get("status") or "").upper()
            if status in ("SOLDOUT", "NOLONGERONSALE"):
                title = f"{title} - Agotado"
            out[f"releaseName{i+1}"] = title
            out[f"price{i+1}"] = fmt_price_eur(t.get("price"))
            out[f"releaseUrl{i+1}"] = (t.get("url") or event_url)
        else:
            out[f"releaseName{i+1}"] = ""
            out[f"price{i+1}"] = ""
            out[f"releaseUrl{i+1}"] = ""
    return out

def looks_like_verification(html: str) -> bool:
    """Detectar páginas de verificación/captcha con más precisión"""
    h = (html or "").lower()
    strong_indicators = [
        "attention required!",
        "just a moment...",
        "hcaptcha",
        "data-sitekey",
        "cf-chl-",
        "why did this happen?",
        "cloudflare",
        "security check",
        "human verification",
        "are you a robot",
        "i'm not a robot",
        "verify you are human",
        "anti-bot",
        "bot detection"
    ]
    
    # Buscar indicadores fuertes
    if any(s in h for s in strong_indicators):
        return True
    
    # Buscar patrones de captcha específicos
    captcha_patterns = [
        r'g-recaptcha',
        r'cf-browser-verification',
        r'challenge-platform',
        r'turnstile',
        r'captcha-container'
    ]
    
    for pattern in captcha_patterns:
        if re.search(pattern, h, re.IGNORECASE):
            return True
    
    return False

def simulate_human_behavior(driver: Driver):
    """Simular comportamiento humano para evitar detección"""
    try:
        # Movimientos de mouse aleatorios
        viewport_width = driver.execute_script("return window.innerWidth;")
        viewport_height = driver.execute_script("return window.innerHeight;")
        
        # Mover mouse a posiciones aleatorias
        for _ in range(random.randint(1, 3)):
            x = random.randint(100, viewport_width - 100)
            y = random.randint(100, viewport_height - 100)
            driver.move_to(x, y)
            time.sleep(random.uniform(0.1, 0.3))
        
        # Scroll aleatorio
        if random.random() > 0.5:
            scroll_amount = random.randint(100, 500)
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.2, 0.5))
            
            # Scroll back
            driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")
            time.sleep(random.uniform(0.1, 0.3))
    
    except Exception as e:
        log(f"[WARN] Error simulando comportamiento humano: {e}")

def setup_stealth_driver(driver: Driver):
    """Configurar el driver para ser más sigiloso"""
    try:
        # Eliminar propiedades que delatan bots
        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        0: {type: "application/x-google-chrome-pdf"},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin"
                    }
                ],
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['es-ES', 'es', 'en'],
            });
        """)
        
        # Establecer un user agent realista
        user_agent = get_random_user_agent()
        driver.execute_script(f"Object.defineProperty(navigator, 'userAgent', {{get: () => '{user_agent}'}});")
        
    except Exception as e:
        log(f"[WARN] Error configurando driver sigiloso: {e}")

def handle_captcha_situation(driver: Driver, url: str, retry_count: int = 0):
    """Manejar situaciones de captcha con diferentes estrategias"""
    if retry_count >= MAX_RETRIES:
        log(f"[FAIL] Máximo de reintentos alcanzado para {url}")
        return False
    
    log(f"[CAPTCHA] Detectado captcha en {url}, intento {retry_count + 1}/{MAX_RETRIES}")
    
    strategies = [
        # Estrategia 1: Esperar y recargar
        lambda: time.sleep(random.uniform(10, 20)) or driver.get(url),
        
        # Estrategia 2: Limpiar cookies y recargar
        lambda: driver.delete_all_cookies() or time.sleep(2) or driver.get(url),
        
        # Estrategia 3: Cambiar user agent y recargar
        lambda: setup_stealth_driver(driver) or time.sleep(2) or driver.get(url),
        
        # Estrategia 4: Esperar más tiempo (para captchas manuales)
        lambda: time.sleep(random.uniform(30, 60)) or driver.get(url)
    ]
    
    try:
        strategy = strategies[min(retry_count, len(strategies) - 1)]
        strategy()
        human_delay(3000, 5000)
        
        # Verificar si todavía hay captcha
        html = driver.page_html
        if not looks_like_verification(html):
            log(f"[SUCCESS] Captcha resuelto en {url}")
            return True
        else:
            return handle_captcha_situation(driver, url, retry_count + 1)
            
    except Exception as e:
        log(f"[ERROR] Error manejando captcha: {e}")
        return False

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

    # Configurar driver sigiloso
    setup_stealth_driver(driver)
    human_delay()

    # 1) Página del club
    club_url = f"https://es.ra.co/clubs/{club_id}/events"
    log(f"[START] Procesando club {club_id} ({club_name})")
    
    try:
        driver.get(club_url)
        human_delay(4000, 7000)  # Espera larga para simular lectura humana
        
        # Siempre simular comportamiento humano
        simulate_human_behavior(driver)
        human_delay(2000, 4000)  # Pausa después de comportamiento
        
        html = driver.page_html
        
        # Manejar captcha si es detectado
        if looks_like_verification(html):
            log(f"[CAPTCHA] Verificación detectada en club {club_id}")
            if not handle_captcha_situation(driver, club_url):
                return {"club_id": club_id, "rows": [], "error": "verification_failed"}
            # Obtener HTML después de manejar captcha
            html = driver.page_html

        ids = extract_event_ids_from_club_html(html)
        if not ids:
            log(f"[WARN] No se encontraron eventIds en club {club_id}.")
            return {"club_id": club_id, "rows": []}

        log(f"[INFO] Club {club_id} ({club_name}) → {len(ids)} eventIds (hasta {max_events})")

        rows_out: List[Dict[str, Any]] = []
        processed_events = 0

        # 2) Eventos
        for ev_id in ids[:max_events]:
            event_url = f"https://es.ra.co/events/{ev_id}"
            event_retry_count = 0
            
            while event_retry_count < MAX_RETRIES:
                try:
                    # Simular comportamiento humano solo cuando sea necesario
                    if event_retry_count > 0:
                        human_delay()
                        simulate_human_behavior(driver)
                    elif processed_events > 0 and random.random() > 0.8:  # 20% de probabilidad
                        human_delay(500, 1000)  # Delay más corto
                        simulate_human_behavior(driver)
                    
                    driver.get(event_url)
                    human_delay(3000, 5000)  # Espera larga para simular lectura de evento
                    
                    # Siempre simular comportamiento humano después de cargar
                    simulate_human_behavior(driver)
                    human_delay(2000, 3000)  # Pausa después de comportamiento
                    
                    page_html = driver.page_html
                    
                    # Verificar captcha en página de evento
                    if looks_like_verification(page_html):
                        log(f"[CAPTCHA] Verificación en evento {ev_id}")
                        if not handle_captcha_situation(driver, event_url):
                            log(f"[SKIP] Evento {ev_id} omitido por captcha")
                            break
                        page_html = driver.page_html
                    
                    # Espera inteligente para carga de contenido
                    content_loaded = False
                    for attempt in range(5):
                        soup = soupify(driver)
                        meta = extract_jsonld(soup)
                        generos = extract_genres_from_html(soup)
                        
                        if meta.get("name") or meta.get("startDate") or meta.get("endDate"):
                            rows_out.append(build_price_row(event_url, page_html, meta, generos))
                            log(f"[OK] {ev_id} → '{meta.get('name','') or ''}'")
                            processed_events += 1
                            content_loaded = True
                            break
                        
                        if attempt < 4:
                            time.sleep(0.5 + random.random()*0.6)
                    
                    if content_loaded:
                        break
                    else:
                        log(f"[WARN] No se pudo cargar contenido para evento {ev_id}")
                        event_retry_count += 1
                        if event_retry_count < MAX_RETRIES:
                            log(f"[RETRY] Reintentando evento {ev_id} ({event_retry_count + 1}/{MAX_RETRIES})")
                        continue

                except Exception as e:
                    log(f"[ERR] {ev_id} → {e}")
                    event_retry_count += 1
                    if event_retry_count < MAX_RETRIES:
                        human_delay(2000, 4000)
                        log(f"[RETRY] Reintentando evento {ev_id} por error ({event_retry_count + 1}/{MAX_RETRIES})")
                    continue
            
            # Pausa larga entre eventos para simular comportamiento humano natural
            if processed_events < len(ids[:max_events]) - 1:
                human_delay(5000, 8000)  # Pausa de 5-8 segundos entre eventos
                
                # Simular comportamiento humano entre eventos
                if random.random() > 0.3:  # 70% de probabilidad
                    simulate_human_behavior(driver)
                    human_delay(2000, 3000)

        log(f"[DONE] Club {club_id}: {len(rows_out)} filas generadas de {len(ids[:max_events])} eventos")
        return {"club_id": club_id, "rows": rows_out}
        
    except Exception as e:
        log(f"[CRITICAL] Error crítico en club {club_id}: {e}")
        return {"club_id": club_id, "rows": [], "error": str(e)}

# ========= Orquestador multi-club =========
def run_all_clubs(club_ids: List[int], max_events_per_club: int) -> List[Dict[str, Any]]:
    all_rows: List[Dict[str, Any]] = []
    seen_urls = set()  # dedup por URL del evento
    failed_clubs = []

    log(f"[START] Iniciando scraping de {len(club_ids)} clubs")
    
    if ENABLE_PARALLEL and len(club_ids) > 1:
        # Procesamiento paralelo para mayor velocidad
        log(f"[PARALLEL] Procesando {len(club_ids)} clubs en paralelo con {MAX_WORKERS} workers")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Crear futuros para cada club
            future_to_club = {
                executor.submit(scrape_club, {"club_id": cid, "max_events": max_events_per_club}): cid 
                for cid in club_ids
            }
            
            # Procesar resultados a medida que se completan
            for future in as_completed(future_to_club):
                cid = future_to_club[future]
                club_name = CLUB_NAMES.get(cid, "Unknown Club")
                
                try:
                    res = future.result()
                    log(f"[PROGRESS] Club {cid} ({club_name}) completado")

                    chunks = []
                    if isinstance(res, dict) and "rows" in res:
                        chunks = res["rows"]
                        if res.get("error"):
                            failed_clubs.append({"club_id": cid, "error": res["error"]})
                    elif isinstance(res, list):
                        for item in res:
                            if isinstance(item, dict) and "rows" in item:
                                chunks.extend(item["rows"])

                    added = 0
                    for row in chunks:
                        url = row.get("url")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_rows.append(row)
                            added += 1

                    log(f"[MERGE] Club {cid}: +{added} filas → total {len(all_rows)}")
                    
                except Exception as e:
                    log(f"[ERROR] Error procesando club {cid}: {e}")
                    failed_clubs.append({"club_id": cid, "error": str(e)})
                    continue
                    
    else:
        # Procesamiento secuencial (fallback)
        log(f"[SEQUENTIAL] Procesando {len(club_ids)} clubs secuencialmente")
        
        for i, cid in enumerate(club_ids):
            club_name = CLUB_NAMES.get(cid, "Unknown Club")
            log(f"[PROGRESS] Procesando club {i+1}/{len(club_ids)}: {cid} ({club_name})")
            
            try:
                res = scrape_club({"club_id": cid, "max_events": max_events_per_club})

                chunks = []
                if isinstance(res, dict) and "rows" in res:
                    chunks = res["rows"]
                    if res.get("error"):
                        failed_clubs.append({"club_id": cid, "error": res["error"]})
                elif isinstance(res, list):
                    for item in res:
                        if isinstance(item, dict) and "rows" in item:
                            chunks.extend(item["rows"])

                added = 0
                for row in chunks:
                    url = row.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_rows.append(row)
                        added += 1

                log(f"[MERGE] Club {cid}: +{added} filas → total {len(all_rows)}")
                
                # Pausa más corta entre clubs en modo secuencial
                if i < len(club_ids) - 1:
                    log(f"[PAUSE] Pausa entre clubs...")
                    human_delay(2000, 4000)  # Reducido a 2-4 segundos
                    
            except Exception as e:
                log(f"[ERROR] Error procesando club {cid}: {e}")
                failed_clubs.append({"club_id": cid, "error": str(e)})
                continue

    # Resumen final
    log(f"[SUMMARY] Scraping completado:")
    log(f"  - Total filas: {len(all_rows)}")
    log(f"  - Clubs procesados: {len(club_ids)}")
    log(f"  - Clubs fallidos: {len(failed_clubs)}")
    
    if failed_clubs:
        log(f"[FAILED] Clubs con errores:")
        for failed in failed_clubs:
            club_name = CLUB_NAMES.get(failed["club_id"], "Unknown")
            log(f"  - {failed['club_id']} ({club_name}): {failed['error']}")

    return all_rows

# ========= Main =========
if __name__ == "__main__":
    rows = run_all_clubs(CLUB_IDS, MAX_EVENTS_PER_CLUB)
    os.makedirs("output", exist_ok=True)
    out_path = "output/ra_all.json"  # <- nombre que pediste
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\nGuardadas {len(rows)} filas en {out_path}")
