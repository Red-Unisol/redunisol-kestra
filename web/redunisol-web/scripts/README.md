Scraper scripts to generate database seed JSON for pages

Prereqs:
- Node 18+
- Install dependencies in project root: `npm i axios cheerio`

Usage:
- Single slug:
  node scripts/scrape-seed.js por-que-convienen-prestamos-empleados-publicos-la-rioja

- From file with slugs (one per line):
  node scripts/scrape-seed.js -f slugs.txt

Output:
- Writes `database/seeders/scraped_seed.json` which is imported by the `ScrapedPagesSeeder`.

Seeding into DB:
- Run `php artisan db:seed --class=Database\Seeders\ScrapedPagesSeeder` (or run full `DatabaseSeeder`).
