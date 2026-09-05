# Image Extraction

How to extract product images from listing pages via Playwright.

## Steps

1. Find the product image: `document.querySelector('img[alt*="Product photo"]')` (Facebook) or `meta[property="og:image"]` (eBay)
2. Fallback: First `img` with `naturalWidth >= 300` excluding profile pics/emojis
3. Download the image blob via in-browser `fetch()` while on the listing's domain (this inherits the session cookies needed for CDN auth)
4. Convert to base64 with `FileReader.readAsDataURL()`, return to the host, and save as `${CLAUDE_PLUGIN_DATA}/data/images/{listing_id}.jpg`
5. Set `image_url` in the CSV to the local path: `/data/images/{listing_id}.jpg`

## Browser Code Pattern

Use `browser_run_code` to extract and fetch the image in a single evaluate call per listing:

```javascript
const b64 = await page.evaluate(async () => {
  let img = document.querySelector('img[alt*="Product photo"]');
  if (!img) img = [...document.querySelectorAll('img')].find(i =>
    (i.src.includes('t45.5328') || i.src.includes('t0.65075')) && i.naturalWidth >= 150);
  if (!img?.src) return null;
  const resp = await fetch(img.src);
  if (!resp.ok) return null;
  const buf = await resp.arrayBuffer();
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
});
// Then save: writeFileSync(`${CLAUDE_PLUGIN_DATA}/data/images/${id}.jpg`, Buffer.from(b64, 'base64'))
```

## Fallback

Leave `image_url` empty if no image can be extracted — the dashboard shows a styled placeholder with the search term.
