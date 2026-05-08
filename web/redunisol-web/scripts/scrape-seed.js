import axios from 'axios';
import { load } from 'cheerio';
import fs from 'fs/promises';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'https://prestamos.redunisol.com.ar';
const CONCURRENCY = Number(process.env.CONCURRENCY) || 5;
const MAX_RETRIES = Number(process.env.MAX_RETRIES) || 3;
const BACKOFF_BASE_MS = Number(process.env.BACKOFF_BASE_MS) || 500; // exponential base

function absUrl(src, base) {
    if (!src) return null;
    try {
        return new URL(src, base).href;
    } catch (e) {
        return src;
    }
}

function isFullUrl(s) {
    return /^https?:\/\//i.test(s);
}

function isLikelySlug(s) {
    if (!s || typeof s !== 'string') return false;
    // allow letters, numbers, hyphens, slashes, underscores
    return /^[\w\-/]+$/.test(s);
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetries(url) {
    let attempt = 0;
    while (attempt < MAX_RETRIES) {
        attempt++;
        try {
            const res = await axios.get(url, {
                headers: {
                    'User-Agent': 'scraper-bot/1.0 (+https://example.com)',
                },
                timeout: 20000,
                validateStatus: (s) => true, // we'll handle statuses ourselves
            });

            // treat 2xx as success
            if (res.status >= 200 && res.status < 300) return res;

            // 404/4xx are definitive (no retry)
            if (res.status >= 400 && res.status < 500) {
                const err = new Error(`HTTP ${res.status}`);
                err.response = res;
                throw err;
            }

            // 5xx -> retry
            if (res.status >= 500) {
                const backoff = BACKOFF_BASE_MS * Math.pow(2, attempt - 1);
                await sleep(backoff);
                continue;
            }

            // other statuses -> treat as error
            const err = new Error(`HTTP ${res.status}`);
            err.response = res;
            throw err;
        } catch (err) {
            // If it's a definitive 4xx error, rethrow immediately
            if (
                err.response &&
                err.response.status >= 400 &&
                err.response.status < 500
            ) {
                throw err;
            }

            if (attempt >= MAX_RETRIES) throw err;

            const backoff = BACKOFF_BASE_MS * Math.pow(2, attempt - 1);
            await sleep(backoff);
        }
    }
}

async function scrapeSlug(slug) {
    const originalInput = slug;

    // If the input looks like a full URL, use it directly. Otherwise build from BASE_URL + slug
    let url;
    let normalizedSlug;
    if (isFullUrl(slug)) {
        url = slug.endsWith('/') ? slug : slug + '/';
        try {
            normalizedSlug = new URL(url).pathname.replace(/^\/+|\/+$/g, '');
        } catch (e) {
            normalizedSlug = url;
        }
    } else {
        url = `${BASE_URL.replace(/\/$/, '')}/${slug.replace(/^\//, '')}/`;
        normalizedSlug = slug.replace(/^\/+|\/+$/g, '');
    }

    const res = await fetchWithRetries(url);
    const $ = load(res.data);

    const meta = (name) =>
        $('meta[name="' + name + '"]').attr('content') ||
        $('meta[property="' + name + '"]').attr('content');

    const title = meta('og:title') || $('title').text().trim() || null;
    const description = meta('og:description') || meta('description') || null;
    const author =
        meta('author') ||
        meta('article:author') ||
        $('.author').first().text().trim() ||
        null;
    const published_at =
        meta('article:published_time') ||
        $('time[datetime]').attr('datetime') ||
        null;
    const ogImage = meta('og:image') || null;

    // Prefer explicit .entry-content when available (site-specific requirement)
    let contentHtml = '';
    const entry = $('.entry-content').first();
    if (entry && entry.length) {
        contentHtml = entry.html();
    } else {
        // fallback: choose the best content container by text length among candidates
        const contentCandidates = [
            'article',
            '[itemprop="articleBody"]',
            '.post-content',
            '.single-post',
            '#content',
            'main',
            '[role="main"]',
            '.content',
            '.post',
        ];

        let bestEl = null;
        let bestLen = 0;
        for (const s of contentCandidates) {
            const el = $(s).first();
            if (el && el.length) {
                const textLen = (el.text() || '').length;
                if (textLen > bestLen) {
                    bestLen = textLen;
                    bestEl = el;
                }
            }
        }

        if (bestEl) contentHtml = bestEl.html();
        if (!contentHtml) contentHtml = $('body').html() || '';
    }

    // Extract thumbnail image from .attachment-post-thumbnail if present
    const thumbEl = $('.attachment-post-thumbnail').first();
    const thumbSrc =
        thumbEl && thumbEl.length
            ? thumbEl.attr('src') ||
              thumbEl.attr('data-src') ||
              thumbEl.find('img').attr('src')
            : null;
    const thumbImage = thumbSrc ? absUrl(thumbSrc, url) : null;

    // If content didn't include a table but the page contains a large table, include it
    if (!/\<table/i.test(contentHtml)) {
        let bestTable = null;
        let bestTableRows = 0;
        $('table').each((i, t) => {
            const rows = $(t).find('tr').length || 0;
            if (rows > bestTableRows) {
                bestTableRows = rows;
                bestTable = t;
            }
        });
        if (bestTable && bestTableRows >= 3) {
            // prepend the table's outer HTML to the content so we preserve it
            const tableHtml = $.html(bestTable);
            contentHtml = tableHtml + '\n' + contentHtml;
        }
    }

    const contentText = load(contentHtml).text().replace(/\s+/g, ' ').trim();

    // gather images from multiple places (og:image, link rel, img src/srcset/data-src)
    const images = [];
    if (ogImage) images.push(absUrl(ogImage, url));
    const linkImage =
        $('link[rel="image_src"]').attr('href') ||
        $('meta[name="image"]').attr('content');
    if (linkImage) images.push(absUrl(linkImage, url));

    const content$ = load(contentHtml);
    content$('img').each((i, img) => {
        const src =
            content$(img).attr('src') ||
            content$(img).attr('data-src') ||
            content$(img).attr('data-lazy-src');
        if (src) images.push(absUrl(src, url));
        const srcset = content$(img).attr('srcset');
        if (srcset) {
            // take the first URL from srcset
            const first = srcset.split(',')[0].trim().split(' ')[0];
            if (first) images.push(absUrl(first, url));
        }
    });

    // also check images in figures or lazy attributes in the whole doc
    $('figure img').each((i, img) => {
        const src =
            $(img).attr('src') ||
            $(img).attr('data-src') ||
            $(img).attr('data-lazy-src');
        if (src) images.push(absUrl(src, url));
    });

    // include any global images on the page as fallback
    $('img').each((i, img) => {
        const src =
            $(img).attr('src') ||
            $(img).attr('data-src') ||
            $(img).attr('data-lazy-src');
        if (src) images.push(absUrl(src, url));
    });

    // Extract tags/keywords: meta keywords, rel=tag links, and common tag containers
    const tags = new Set();
    const metaKeywords =
        meta('keywords') || $('meta[name="keywords"]').attr('content');
    if (metaKeywords) {
        metaKeywords
            .split(',')
            .map((t) => t.trim())
            .filter(Boolean)
            .forEach((t) => tags.add(t));
    }

    const tagSelectors = [
        '.tags a',
        '.post-tags a',
        'a[rel="tag"]',
        '.tag-list a',
        '.tags li a',
    ];
    for (const s of tagSelectors) {
        $(s).each((i, el) => {
            const t = $(el).text().trim();
            if (t) tags.add(t);
        });
    }

    // also try to extract tags from breadcrumbs or from nearby link texts
    $('.breadcrumb a, .breadcrumbs a, nav[aria-label="breadcrumb"] a').each(
        (i, el) => {
            const t = $(el).text().trim();
            if (t) tags.add(t);
        },
    );

    // normalize images and tags
    const normImages = Array.from(new Set(images))
        .filter(Boolean)
        .map((i) => absUrl(i, url));
    const normTags = Array.from(tags).filter(Boolean);

    return {
        input: originalInput,
        slug: normalizedSlug,
        url,
        title,
        description,
        author,
        published_at,
        content_html: contentHtml,
        content_text: contentText,
        images: normImages,
        thumbnail: thumbImage,
        tags: normTags,
        scraped_at: new Date().toISOString(),
    };
}

// simple concurrency limiter
function pLimit(concurrency) {
    let active = 0;
    const queue = [];
    const next = () => {
        if (queue.length === 0) return;
        if (active >= concurrency) return;
        active++;
        const { fn, resolve, reject } = queue.shift();
        fn()
            .then((r) => {
                resolve(r);
                active--;
                next();
            })
            .catch((e) => {
                reject(e);
                active--;
                next();
            });
    };
    return (fn) =>
        new Promise((resolve, reject) => {
            queue.push({ fn, resolve, reject });
            next();
        });
}

async function main() {
    const args = process.argv.slice(2);
    if (!args.length) {
        console.error(
            'Uso: node scrape-seed.js slug1 slug2 ...  O  node scrape-seed.js -f slugs.txt',
        );
        process.exit(1);
    }

    let slugs = [];
    if (args[0] === '-f') {
        const file = args[1];
        if (!file) {
            console.error('Falta archivo');
            process.exit(1);
        }
        const txt = await fs.readFile(file, 'utf8');
        slugs = txt
            .split(/\r?\n/)
            .map((s) => s.trim())
            .filter(Boolean);
    } else {
        // Auto-detect: if the first arg is a file, use it as a list
        const possibleFile = args[0];
        try {
            const stat = await fs.stat(possibleFile);
            if (stat.isFile()) {
                const txt = await fs.readFile(possibleFile, 'utf8');
                slugs = txt
                    .split(/\r?\n/)
                    .map((s) => s.trim())
                    .filter(Boolean);
            } else {
                slugs = args;
            }
        } catch (e) {
            slugs = args;
        }
    }

    // Validate inputs: separate invalid lines and don't attempt request
    const valid = [];
    const invalidResults = [];
    for (const s of slugs) {
        if (isFullUrl(s) || isLikelySlug(s)) {
            valid.push(s);
        } else {
            invalidResults.push({
                input: s,
                error: 'invalid input (not a slug nor URL)',
            });
        }
    }

    const limit = pLimit(CONCURRENCY);
    const tasks = valid.map((slug) =>
        limit(() =>
            scrapeSlug(slug).catch((err) => {
                // normalize axios errors
                if (err.response && err.response.status) {
                    return {
                        input: slug,
                        error: `Request failed with status code ${err.response.status}`,
                    };
                }
                return { input: slug, error: err.message };
            }),
        ),
    );

    const results = await Promise.all(tasks);

    // combine invalidResults + results
    const allItems = [...invalidResults, ...results];

    const out = { generated_at: new Date().toISOString(), items: allItems };
    const outPath = path.resolve(
        process.cwd(),
        'database/seeders/scraped_seed.json',
    );
    await fs.writeFile(outPath, JSON.stringify(out, null, 2), 'utf8');
    console.log('Guardado en', outPath);
}

if (process.env.NODE_ENV !== 'test')
    main().catch((err) => {
        console.error(err);
        process.exit(1);
    });
