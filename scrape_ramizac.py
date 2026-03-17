"""
╔══════════════════════════════════════════════════════════╗
║        ramizac.com — Full Playwright Scraper             ║
║  Handles: bot detection, lazy images, JS-rendered pages  ║
╚══════════════════════════════════════════════════════════╝

HOW TO RUN:
  1. bash setup.sh          ← run this first (only once)
  2. python scrape_ramizac.py

OUTPUT:
  ramizac_scraped/
  ├── scraped_data.json     ← all content in one file
  ├── images/               ← every image downloaded
  ├── css/                  ← stylesheets saved
  ├── home.html             ← raw HTML per page
  └── summary.txt           ← human-readable summary
"""

import os
import re
import json
import time
import asyncio
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# ── Config ──────────────────────────────────────────────
BASE_URL    = "https://ramizac.com"
OUTPUT_DIR  = "ramizac_scraped"
IMAGES_DIR  = os.path.join(OUTPUT_DIR, "images")
CSS_DIR     = os.path.join(OUTPUT_DIR, "css")
MAX_PAGES   = 30          # max pages to crawl
SCROLL_PX   = 500         # scroll step for lazy loading
DELAY       = 1.5         # seconds between pages (polite)

for d in [OUTPUT_DIR, IMAGES_DIR, CSS_DIR]:
    os.makedirs(d, exist_ok=True)

visited   = set()
all_data  = {}
all_imgs  = set()

# ── Helpers ──────────────────────────────────────────────

def clean_filename(url):
    path = urlparse(url).path.strip("/").replace("/", "_")
    return path if path else "home"

def extract_contact(text):
    phones = re.findall(r"[\+\(]?[\d\s\-\(\)]{7,20}", text)
    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    return {
        "phones": list(set(p.strip() for p in phones if len(p.strip()) > 6)),
        "emails": list(set(emails)),
    }

def download_file(url, folder, prefix=""):
    """Download any file (image, css) and save locally."""
    try:
        filename = os.path.basename(urlparse(url).path)
        if not filename or "." not in filename:
            filename = f"{prefix}{abs(hash(url))}.jpg"
        filepath = os.path.join(folder, filename)
        if os.path.exists(filepath):
            return filename
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, timeout=15, headers=headers)
        if r.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(r.content)
            return filename
    except Exception as e:
        print(f"    ⚠️  Download failed: {url[:60]} — {e}")
    return None

def get_internal_links(soup, base):
    links = set()
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"].strip())
        p = urlparse(full)
        if p.netloc == urlparse(BASE_URL).netloc and "#" not in full:
            links.add(full.rstrip("/"))
    return links

# ── Core scraper (per page) ──────────────────────────────

async def scrape_page(page, url):
    print(f"\n  🔍 {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception as e:
        print(f"    ❌ Failed: {e}")
        return None

    # Scroll to trigger lazy-loaded images
    prev_height = 0
    for _ in range(15):
        await page.evaluate(f"window.scrollBy(0, {SCROLL_PX})")
        await asyncio.sleep(0.4)
        height = await page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # Save raw HTML
    slug = clean_filename(url)
    with open(os.path.join(OUTPUT_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # ── Title & meta ──
    title    = soup.title.string.strip() if soup.title else ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta_tag.get("content", "") if meta_tag else ""

    # ── Headings ──
    headings = {}
    for lvl in ["h1", "h2", "h3", "h4"]:
        headings[lvl] = [h.get_text(strip=True) for h in soup.find_all(lvl)]

    # ── Clean text ──
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)

    # ── Images (including lazy-loaded, srcset, data-src) ──
    images = []
    for img in soup.find_all("img"):
        src = (
            img.get("src") or
            img.get("data-src") or
            img.get("data-lazy-src") or
            img.get("data-original") or
            img.get("data-lazysrc")
        )
        # Also check srcset
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            first = srcset.split(",")[0].split(" ")[0].strip()
            if first:
                src = src or first
        if src and not src.startswith("data:"):
            full_src = urljoin(url, src)
            alt = img.get("alt", "")
            if full_src not in all_imgs:
                all_imgs.add(full_src)
                local = download_file(full_src, IMAGES_DIR, "img_")
                images.append({"url": full_src, "alt": alt, "local": local})
                print(f"    🖼️  {os.path.basename(full_src)}")

    # ── CSS background images ──
    bg_imgs = re.findall(r'url\(["\']?([^"\')\s]+)["\']?\)', html)
    for bg in bg_imgs:
        if any(ext in bg.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"]):
            full_bg = urljoin(url, bg)
            if full_bg not in all_imgs:
                all_imgs.add(full_bg)
                local = download_file(full_bg, IMAGES_DIR, "bg_")
                images.append({"url": full_bg, "alt": "background", "local": local})
                print(f"    🎨  bg: {os.path.basename(full_bg)}")

    # ── Stylesheets ──
    stylesheets = []
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href")
        if href:
            full_href = urljoin(url, href)
            local = download_file(full_href, CSS_DIR, "style_")
            stylesheets.append({"url": full_href, "local": local})

    # ── Contact info ──
    contact = extract_contact(text)

    # ── Navigation ──
    nav_links = []
    nav = soup.find("nav") or soup.find(class_=re.compile(r"nav|menu|header", re.I))
    if nav:
        for a in nav.find_all("a", href=True):
            nav_links.append({"text": a.get_text(strip=True), "href": a["href"]})

    # ── Sections ──
    sections = []
    for section in soup.find_all(["section", "div"], class_=True):
        classes = " ".join(section.get("class", []))
        section_text = section.get_text(strip=True)
        if len(section_text) > 50:
            sections.append({"classes": classes, "text": section_text[:300]})

    # ── Internal links for crawling ──
    internal_links = get_internal_links(soup, url)

    return {
        "url":             url,
        "title":           title,
        "meta_description": meta_desc,
        "headings":        headings,
        "text":            text,
        "images":          images,
        "stylesheets":     stylesheets,
        "contact":         contact,
        "nav_links":       nav_links,
        "sections":        sections[:20],
        "internal_links":  list(internal_links),
    }

# ── Main crawler ─────────────────────────────────────────

async def crawl():
    print("\n" + "═"*55)
    print("  🌐 ramizac.com — Playwright Scraper Starting")
    print("═"*55)

    queue = [BASE_URL]
    visited.add(BASE_URL.rstrip("/"))

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        # Hide automation signals
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        while queue and len(all_data) < MAX_PAGES:
            url = queue.pop(0)
            data = await scrape_page(page, url)
            if not data:
                continue

            all_data[url] = data
            print(f"    ✅ Done — {len(data['images'])} images, {len(data['internal_links'])} links found")

            for link in data["internal_links"]:
                if link not in visited:
                    visited.add(link)
                    queue.append(link)

            await asyncio.sleep(DELAY)

        await browser.close()

    print(f"\n{'═'*55}")
    print(f"  ✅ Crawled {len(all_data)} pages | {len(all_imgs)} images total")
    print(f"{'═'*55}\n")

# ── Save outputs ─────────────────────────────────────────

def save_results():
    # JSON
    json_path = os.path.join(OUTPUT_DIR, "scraped_data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"  📦 JSON saved:    {json_path}")

    # Human-readable summary
    summary_path = os.path.join(OUTPUT_DIR, "summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("RAMIZAC.COM — SCRAPED CONTENT SUMMARY\n")
        f.write("="*50 + "\n\n")
        for url, data in all_data.items():
            f.write(f"PAGE: {data['title']}\n")
            f.write(f"URL:  {url}\n")
            f.write(f"Meta: {data['meta_description']}\n")
            for lvl, texts in data['headings'].items():
                if texts:
                    f.write(f"{lvl.upper()}: {', '.join(texts)}\n")
            if data['contact']['emails']:
                f.write(f"Emails: {', '.join(data['contact']['emails'])}\n")
            if data['contact']['phones']:
                f.write(f"Phones: {', '.join(data['contact']['phones'][:3])}\n")
            f.write(f"Images: {len(data['images'])}\n")
            f.write("\n" + "-"*40 + "\n\n")
    print(f"  📄 Summary saved: {summary_path}")

    # Final folder overview
    img_count = len([f for f in os.listdir(IMAGES_DIR)])
    css_count = len([f for f in os.listdir(CSS_DIR)])
    print(f"\n  📁 Output folder: {OUTPUT_DIR}/")
    print(f"     ├── scraped_data.json")
    print(f"     ├── summary.txt")
    print(f"     ├── images/  ({img_count} files)")
    print(f"     ├── css/     ({css_count} files)")
    print(f"     └── *.html   ({len(all_data)} pages)")

# ── Entry point ──────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(crawl())
    save_results()
    print("\n🎉 Scraping complete! Share scraped_data.json here and I'll build your new site.\n")