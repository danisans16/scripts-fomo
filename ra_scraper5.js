const { chromium } = require('playwright-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

chromium.use(StealthPlugin());

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const clubIds = [911, 150612, 195409, 3818, 3760, 60710, 2072, 2253, 216950];
  const allEvents = {};

  for (const id of clubIds) {
    const url = `https://es.ra.co/clubs/${id}/events`;
    console.log(`Extrayendo eventos de club ${id} -> ${url}`);

    await page.goto(url, { waitUntil: 'networkidle' });

    const eventsMap = new Map();
    const viewportHeight = await page.evaluate(() => window.innerHeight);

    let lastScroll = 0;
    while (true) {
      // Scroll chunk por chunk
      await page.evaluate((vh) => window.scrollBy(0, vh), viewportHeight);
      await page.waitForTimeout(500);

      // Extraer los eventos visibles en este momento (Script 2)
      const visibleEvents = await page.$$eval('[data-testid="event-listing-card"]', cards => {
        return cards.map(card => {
          const titleEl = card.querySelector('[data-pw-test-id="event-title-link"]');
          const dateEl = card.querySelector('span[data-test-id="event-listing-heading"], span.Text-sc-wks9sf-0.loAMdA');
          const linkEl = card.querySelector('a[data-pw-test-id="event-title-link"]');

          // Script 1: <img> cl�sico
          let imgSrcs = [];
          const imgEl = card.querySelector('a[data-pw-test-id="event-image-link"] img');
          if (imgEl) imgSrcs.push(imgEl.getAttribute('src'));

          // Script 1: scroll completo fallback
          const lazyImgs = card.querySelectorAll('a[data-pw-test-id="event-image-link"] img');
          lazyImgs.forEach(img => {
            const src = img.getAttribute('src');
            if (src && !imgSrcs.includes(src)) imgSrcs.push(src);
          });

          return {
            nombre: titleEl ? titleEl.innerText.trim() : null,
            fecha: dateEl ? dateEl.innerText.trim() : null,
            url_evento: linkEl ? linkEl.href : null,
            url_imagenes: imgSrcs // array con todas las URLs obtenidas
          };
        });
      });

      // Guardar en Map para evitar duplicados
      visibleEvents.forEach(e => {
        if (e.url_evento) {
          if (!eventsMap.has(e.url_evento)) {
            eventsMap.set(e.url_evento, e);
          } else {
            // combinar URLs si ya existe el evento
            const existing = eventsMap.get(e.url_evento);
            e.url_imagenes.forEach(src => {
              if (!existing.url_imagenes.includes(src)) existing.url_imagenes.push(src);
            });
            eventsMap.set(e.url_evento, existing);
          }
        }
      });

      // Revisar si llegamos al final
      const scrollHeight = await page.evaluate(() => document.body.scrollHeight);
      const scrollTop = await page.evaluate(() => window.scrollY + window.innerHeight);
      if (scrollTop >= scrollHeight) break;
    }

    allEvents[id] = Array.from(eventsMap.values());
  }

  console.log(JSON.stringify(allEvents, null, 2));
  await browser.close();
})();