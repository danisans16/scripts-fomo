const puppeteer = require('puppeteer');
const fs = require('fs');

const venues = [
  'twenties-barcelona',
  'bling-bling-bcn',
  'pacha-barcelona',
  'sutton-barcelona',
  'la-biblio-bcn',
  'duvet',
  'el-cuatro',
  'opium-barcelona',
  'sala-b1',
  'sala-bikini',
  'el-rodeo-club1',
  'opulent-society',
  'yass-barcelona',
  'colors',
  'new-york-disco',
  'draco-disco',
  'sugar-barcelona',
  'otto-zutz',
  'exclusive-nights',
  'luz-de-gas',
  'costa-breve3',
  'discoteca-illusion-barcelona',
  'downtown-barcelona',
  'wolf-barcelona',
  'carpe-diem-barcelona'
];

const venueMap = { 
  'twenties-barcelona': 'Twenties',
  'bling-bling-bcn': 'Bling Bling',
  'pacha-barcelona': 'Pacha',
  'sutton-barcelona': 'Sutton',
  'la-biblio-bcn': 'La Biblio',
  'duvet': 'Duvet',
  'el-cuatro': 'El Cuatro',
  'opium-barcelona': 'Opium',
  'sala-b1': 'Sala B',
  'sala-bikini': 'Sala Bikini',
  'el-rodeo-club1': 'El Rodeo Club',
  'opulent-society': 'Opulent Society',
  'yass-barcelona': 'Yass',
  'colors': 'Colors',
  'new-york-disco': 'New York Disco',
  'draco-disco': 'Draco Disco',
  'sugar-barcelona': 'Sugar',
  'otto-zutz': 'Otto Zutz',
  'exclusive-nights': 'Exclusive Nights',
  'luz-de-gas': 'Luz De Gas',
  'costa-breve3': 'Costa Breve',
  'discoteca-illusion-barcelona': 'Discoteca Illusion',
  'downtown-barcelona': 'Downtown',
  'wolf-barcelona': 'Wolf',
  'carpe-diem-barcelona': 'Carpe Diem'
};

(async () => {
  console.log('Iniciando navegador...');
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();

  const allResults = [];
  const venuesWithoutEvents = [];

  for (const venue of venues) {
    console.log(`\n==== Procesando discoteca: ${venue} ====`);
    const urlBase = `https://www.fourvenues.com/es/iframe/${venue}?theme=dark`;
    console.log(`Abriendo página: ${urlBase}`);

    try {
      await page.goto(urlBase, { waitUntil: 'networkidle2', timeout: 30000 });
      await page.waitForSelector('#contenido', { timeout: 10000 }).catch(() => {});

      const frame = page.frames().find(f => f.url().includes(venue));

      let events = [];

      // Método 1: dentro del frame si existe
      if (frame) {
        events = await frame.evaluate((venue) => {
          const nodes = [...document.querySelectorAll('div[onclick^="listadoEventosComponent.onClickEvent"]')];

          return nodes.map(div => {
            const onclick = div.getAttribute('onclick') || '';
            const regex = /onClickEvent\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]/;
            const match = onclick.match(regex);
            if (!match) return null;

            const [, eventId, code] = match;

            const dateEl = div.querySelector('div.subtitle h2');
            const dateText = dateEl ? dateEl.innerText.trim() : null;

            const timeEl = div.querySelector('div.subtitle.text-xs.sm\\:text-sm:nth-child(2)');
            const time = timeEl ? timeEl.innerText.trim().replace(/\s+/g, ' ') : null;

            const nameEl = div.querySelector('div.info-container p.font-semibold');
            const name = nameEl ? nameEl.innerText.trim() : null;

            const url = `https://www.fourvenues.com/es/iframe/${venue}/events/${eventId}-${code}?theme=dark`;

            const imageDiv = div.querySelector('div[class*="bg-cover"]');
            let imageUrl = null;
            if (imageDiv) {
              const style = imageDiv.getAttribute('style');
              const imageMatch = style && style.match(/url\(['"]?(.*?)['"]?\)/);
              imageUrl = imageMatch ? imageMatch[1] : null;
            }

            return { name, dateText, time, eventId, code, venue, url, imageUrl };
          }).filter(e => e !== null);
        }, venue);
      }

      // Método 2: directo al DOM principal
      if (!events.length) {
        events = await page.evaluate((venue) => {
          const nodes = [...document.querySelectorAll('div[onclick*="listadoEventosComponent.onClickEvent"]')];

          return nodes.map(div => {
            const onclick = div.getAttribute('onclick') || '';
            const regex = /onClickEvent\(\s*'([^']+)'\s*,\s*'([^']+)'/;
            const match = onclick.match(regex);
            if (!match) return null;

            const [ , eventId, code ] = match;

            const dateText = div.querySelector('.subtitle h2')?.innerText?.trim() || null;
            const time = div.querySelector('.subtitle.text-xs.sm\\:text-sm')?.innerText?.trim() || null;
            const name = div.querySelector('.info-container p')?.innerText?.trim() || null;

            const url = `https://www.fourvenues.com/es/iframe/${venue}/events/${eventId}-${code}?theme=dark`;

            let imageUrl = null;
            const style = div.querySelector('[style*="background-image"]')?.getAttribute('style');
            if (style) {
              const m = style.match(/url\(['"]?(.*?)['"]?\)/);
              if (m) imageUrl = m[1];
            }

            return { name, dateText, time, eventId, code, venue, url, imageUrl };
          }).filter(e => e);
        }, venue);
      }

      console.log(`Se encontraron ${events.length} eventos en ${venue}.`);
      if (!events.length) venuesWithoutEvents.push(venue);

      for (let i = 0; i < events.length; i++) {
        const event = events[i];
        console.log(`Visitando evento (${i + 1}/${events.length}): ${event.url}`);

        try {
          await page.goto(event.url, { waitUntil: 'networkidle2', timeout: 30000 });

          // Buscar si el contenido está dentro de un frame (muy importante)
          const eventFrame = page.frames().find(f => {
            const u = f.url() || '';
            return (u.includes(`/events/${event.eventId}`) || (u.includes(event.venue) && u.includes('/events/')));
          });

          if (eventFrame) {
            console.log(`Extrayendo dentro del frame: ${eventFrame.url()}`);
          } else {
            console.log('Extrayendo en la página principal (no se encontró frame específico)');
          }

          // --- EVALUACIÓN: extracción robusta basada en "tarifas" + fallback DOM ---
          const eventReleases = await (eventFrame ? eventFrame : page).evaluate(() => {
            const clean = s => (s ? s.trim().replace(/\s+/g, ' ') : null);

            // 1) Obtener tarifas (window.tarifas o buscar "const tarifas = {...};" en scripts)
            let tarifasObj = null;
            try {
              if (typeof window !== 'undefined' && window.tarifas) tarifasObj = window.tarifas;
            } catch (e) { tarifasObj = null; }

            if (!tarifasObj) {
              const scripts = [...document.querySelectorAll('script')];
              for (const s of scripts) {
                const t = s.innerText || '';
                if (!t) continue;
                const m = t.match(/tarifas\s*=\s*(\{[\s\S]*?\});/);
                if (m && m[1]) {
                  try {
                    tarifasObj = JSON.parse(m[1]);
                    break;
                  } catch (e) {
                    // intenta limpiar saltos de línea inofensivos
                    try {
                      const cleaned = m[1].replace(/([\r\n\t]+)/g, ' ');
                      tarifasObj = JSON.parse(cleaned);
                      break;
                    } catch (ee) { /* ignore */ }
                  }
                }
              }
            }

            // Helpers para parseo onclick -> url
            const buildReleaseUrl = (onclick) => {
              if (!onclick) return null;
              const m = onclick.match(/ticketsRatesComponent\.onEmitTicket\(\s*'([^']+)'\s*,\s*'([^']+)'/);
              if (!m) return null;
              let basePath = m[1];
              const ticketId = m[2];
              if (basePath.startsWith('/es/iframe')) basePath = basePath.replace(/^\/es\/iframe/, '/es');
              else if (basePath.startsWith('/iframe')) basePath = basePath.replace(/^\/iframe/, '/es');
              else if (!basePath.startsWith('/')) basePath = '/es/' + basePath;
              return `https://www.fourvenues.com${basePath.replace(/\/$/, '')}/${ticketId}`;
            };

            // candidatos ONCLICK (todos los elementos con ticketsRatesComponent.onEmitTicket)
            const onclickElements = [...document.querySelectorAll('[onclick*="ticketsRatesComponent.onEmitTicket"]')].map(el => {
              return {
                onclick: el.getAttribute('onclick'),
                text: (el.innerText || el.textContent || '').trim()
              };
            });

            const numberFromText = (txt) => {
              if (!txt) return null;
              const m = txt.match(/(\d{1,3}(?:[.,]\d{1,2})?)/);
              if (!m) return null;
              return parseFloat(m[1].replace(',', '.'));
            };

            // fallback DOM parsing (tu método original) si no hay tarifasObj
            if (!tarifasObj) {
              const releaseBlocks = [...document.querySelectorAll('#tarifa-name-button-block')];

              const releases = releaseBlocks.map(block => {
                const name = clean(block.querySelector('#tarifa-name')?.innerText);

                let price = clean(block.parentElement?.querySelector('#price-just-one-opcion .text-primary')?.innerText);
                if (!price) {
                  const btnPrice = block.closest('div')?.querySelector('div.font-semibold.text-lg.text-primary');
                  price = clean(btnPrice?.innerText);
                }

                let releaseUrl = null;
                const mainDiv = block.closest('div[onclick*="ticketsRatesComponent.onEmitTicket"]');
                if (mainDiv) {
                  const onclick = mainDiv.getAttribute('onclick') || '';
                  const m = onclick.match(/ticketsRatesComponent\.onEmitTicket\(\s*'([^']+)'\s*,\s*'([^']+)'/);
                  if (m) {
                    let basePath = m[1];
                    const ticketId = m[2];
                    if (basePath.startsWith('/es/iframe')) basePath = basePath.replace(/^\/es\/iframe/, '/es');
                    else if (basePath.startsWith('/iframe')) basePath = basePath.replace(/^\/iframe/, '/es');
                    else if (!basePath.startsWith('/')) basePath = '/es/' + basePath;
                    releaseUrl = `https://www.fourvenues.com${basePath.replace(/\/$/, '')}/${ticketId}`;
                  }
                }

                return { releaseName: name, price, releaseUrl };
              }).filter(r => r.releaseName || r.price || r.releaseUrl);

              // currentRelease fallback: primera con releaseUrl
              const cur = releases.find(r => r.releaseUrl);
              return { releases, currentRelease: cur ? cur.releaseName : (releases[0] ? releases[0].releaseName : null) };
            }

            // Si tenemos tarifasObj, generar releases desde ahí (regla solicitada)
            const releases = [];

            const entradas = Array.isArray(tarifasObj.entradas) ? tarifasObj.entradas : [];

            entradas.forEach(t => {
              const tName = clean(t.nombre) || '';
              const opciones = Array.isArray(t.opciones) ? t.opciones : [];

              const anyNamed = opciones.some(o => (o.name || '').trim() !== '');

              if (anyNamed) {
                // crear una release por cada opción con name no vacío
                opciones.forEach(opt => {
                  if ((opt.name || '').trim() === '') return; // ignorar opciones sin nombre cuando existen opciones nombradas
                  const optName = clean(opt.name);
                  const optPriceNum = (opt.precio !== undefined && opt.precio !== null) ? Number(opt.precio) : null;
                  const priceText = optPriceNum !== null ? (Number.isInteger(optPriceNum) ? `${optPriceNum}€` : `${optPriceNum}€`) : (t.precioStr || null);

                  // buscar candidato por nombre primero, luego por precio numérico
                  let candidate = onclickElements.find(c => c.text && optName && c.text.toLowerCase().includes(optName.toLowerCase()));
                  if (!candidate && optPriceNum !== null) {
                    candidate = onclickElements.find(c => {
                      const n = numberFromText(c.text);
                      return n !== null && Math.abs(n - optPriceNum) < 0.5;
                    });
                  }
                  const releaseUrl = candidate ? buildReleaseUrl(candidate.onclick) : null;
                  releases.push({ releaseName: optName || tName, price: priceText, releaseUrl });
                });
              } else {
                // ninguna opción tiene nombre -> crear UNA release con el nombre del encabezado y precio de la opción actual
                const chosen = opciones.find(o => o.actual) || opciones[0] || null;
                const chosenPriceNum = chosen && chosen.precio !== undefined && chosen.precio !== null ? Number(chosen.precio) : (t.precio !== undefined ? Number(t.precio) : null);
                const priceText = chosenPriceNum !== null ? (Number.isInteger(chosenPriceNum) ? `${chosenPriceNum}€` : `${chosenPriceNum}€`) : (t.precioStr || null);

                // buscar candidato por precio (preferible) o por nombre de tarifa
                let candidate = null;
                if (chosenPriceNum !== null) {
                  candidate = onclickElements.find(c => {
                    const n = numberFromText(c.text);
                    return n !== null && Math.abs(n - chosenPriceNum) < 0.5;
                  });
                }
                if (!candidate && tName) {
                  candidate = onclickElements.find(c => c.text && c.text.toLowerCase().includes(tName.toLowerCase()));
                }

                const releaseUrl = candidate ? buildReleaseUrl(candidate.onclick) : null;
                releases.push({ releaseName: tName, price: priceText, releaseUrl });
              }
            });

            // determinar currentRelease basado en tarifasObj (regla: opción actual => releaseName correspondiente)
            let currentRelease = null;
            for (const t of entradas) {
              const opciones = Array.isArray(t.opciones) ? t.opciones : [];
              const anyNamed = opciones.some(o => (o.name || '').trim() !== '');
              if (anyNamed) {
                const actualOpt = opciones.find(o => o.actual && (o.name || '').trim() !== '');
                if (actualOpt) {
                  currentRelease = clean(actualOpt.name);
                  break;
                }
              } else {
                const actualOpt = opciones.find(o => o.actual) || opciones[0];
                if (actualOpt) {
                  currentRelease = clean(t.nombre);
                  break;
                }
              }
            }

            return { releases, currentRelease };
          });

          // --- FIN EVALUACIÓN ---

          // Añado flattening para que tengas releaseName1..6, price1..6, releaseUrl1..6 como en tus ejemplos
          const flat = {};
          for (let k = 0; k < 6; k++) {
            const r = eventReleases.releases[k];
            flat[`releaseName${k+1}`] = r ? (r.releaseName || '') : '';
            flat[`price${k+1}`] = r ? (r.price || '') : '';
            flat[`releaseUrl${k+1}`] = r ? (r.releaseUrl || '') : '';
          }

          // Construir objeto final combinando releases + campos planos
          const resultObj = {
            venue: venueMap[event.venue] || event.venue,
            eventName: event.name,
            url: event.url,
            date: event.dateText,
            time: event.time,
            imageUrl: event.imageUrl,
            releases: eventReleases.releases,
            currentRelease: eventReleases.currentRelease,
            ...flat
          };

          // si detectamos fecha 'YYYY-MM-DD' en algún script JSON-LD podríamos añadir event_date; por simplicidad no lo hacemos aquí
          allResults.push(resultObj);

          console.log(`Releases extraídos: ${eventReleases.releases.length}`);
        } catch (err) {
          console.warn(`Error extrayendo info de ${event.url}: ${err.message}`);
        }
      }
    } catch (err) {
      console.warn(`Error procesando discoteca ${venue}: ${err.message}`);
      venuesWithoutEvents.push(venue);
    }
  }

  await browser.close();

  const outputPath = './discosdata.json';
  fs.writeFileSync(outputPath, JSON.stringify(allResults, null, 2));
  console.log(`\nProceso finalizado. Datos guardados en ${outputPath}`);

  if (venuesWithoutEvents.length) {
    console.log('\nDiscotecas sin eventos detectados por ningún método:');
    venuesWithoutEvents.forEach(v => console.log(`- ${v}`));
  }
})();