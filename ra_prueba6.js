// ra_scraper_combined_with_club_event.js
const { chromium } = require('playwright-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fetch = (...args) => import('node-fetch').then(({ default: fetch }) => fetch(...args));
const fs = require('fs');

chromium.use(StealthPlugin());

const GRAPHQL_URL = 'https://es.ra.co/graphql';

const clubIds = [150612, 195409, 3818, 3760, 911, 60710, 2072, 2253, 216950];

const clubNames = {
  911: 'Razzmatazz',
  150612: 'M7 CLUB',
  195409: 'Les Enfants',
  3818: 'Macarena Club',
  3760: 'La Terrazza',
  60710: 'Input',
  2072: 'Nitsa',
  2253: 'Moog',
  216950: 'Noxe'
};

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const allEvents = [];

  for (const clubId of clubIds) {
    const url = `https://es.ra.co/clubs/${clubId}/events`;
    console.log(`Extrayendo eventos de club ${clubId} -> ${url}`);

    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

      const eventIds = await page.$$eval(
        'a[data-pw-test-id="event-title-link"]',
        links => links
          .map(a => {
            const m = (a.href || '').match(/events\/(\d+)/);
            return m ? m[1] : null;
          })
          .filter(Boolean)
      );

      for (const eventId of eventIds) {
        try {
          const body = {
            query: `
              {
                event(id: "${eventId}") {
                  id
                  title
                  contentUrl
                  images {
                    filename
                    type
                  }
                  venue {
                    id
                    name
                  }
                  tickets {
                    title
                    priceRetail
                  }
                  genres {
                    name
                  }
                  startTime
                  endTime
                }
              }
            `
          };

          const res = await fetch(GRAPHQL_URL, {
            method: 'POST',
            headers: {
              'accept': '*/*',
              'accept-encoding': 'gzip, deflate, br',
              'accept-language': 'es-ES,es;q=0.9',
              'content-type': 'application/json',
              'origin': 'https://es.ra.co',
              'referer': `https://es.ra.co/events/${eventId}`,
              'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
            },
            body: JSON.stringify(body)
          });

          const data = await res.json();
          const event = data.data.event;

          if (event) {
            const fecha = new Date(event.startTime).toLocaleDateString('es-ES', { weekday: 'short', day: '2-digit', month: 'short' }).toUpperCase();
            const hora = `${new Date(event.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${new Date(event.endTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
            const generos = event.genres.map(g => g.name).join(', ');
            const url_imagen = event.images?.[0]?.filename || '';
            const clubName = clubNames[clubId] || 'Unknown Club';

            // Separamos disco y evento
            allEvents.push({
              disco: clubName,
              evento: event.title,
              fecha,
              url_evento: `https://es.ra.co/events/${event.id}`,
              generos,
              hora,
              url_imagen
            });
          }

        } catch (err) {
          console.warn(`Error procesando evento ${eventId}: ${err.message || err}`);
        }
      }

    } catch (err) {
      console.warn(`Error procesando club ${clubId}: ${err.message || err}`);
    }
  }

  await browser.close();

  fs.writeFileSync('ra.json', JSON.stringify(allEvents, null, 2), 'utf-8');
  console.log(`Datos guardados en ra.json con ${allEvents.length} eventos.`);
})();
